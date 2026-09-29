# Deployment

Spec §75 asks for this file explicitly; it didn't exist before this
session. Three deployment paths are documented, in the order you'd actually
reach for them:

## 1. Local development - docker-compose (already existed, unchanged)

```bash
cd apps/api
cp .env.example .env   # edit JWT_SECRET at minimum
cd ../..
docker compose up --build
```

This runs Postgres, Redis, and the API in one command, applying
`alembic upgrade head` automatically on boot (see `docker-compose.yml`).
Nothing in this session's additions changed that file - every new
dependency (reportlab, qrcode, prometheus-client, opentelemetry-*, redis)
is already in `apps/api/requirements.txt`, which the existing Dockerfile
already installs from.

**Honesty note applying to this whole file, not just this section**: this
codebase's Dockerfile has never actually been built in the sandbox that
wrote it (no Docker available), and `infrastructure/terraform/` and
`infrastructure/kubernetes/` below have never been run through
`terraform plan`/`kubectl apply` for the same reason (no network, no
Terraform/kubectl binaries, no cloud credentials). Everything here is
written and internally cross-checked (resource references, variable
wiring, security group rules were all verified to actually match each
other) - not proven by execution. Run `terraform validate` and
`terraform plan`, or `kubectl apply --dry-run=server`, yourself before
applying either for real, the same way you'd review a contractor's
otherwise-solid work that's never been deployed.

## 2. Production - AWS via Terraform (`infrastructure/terraform/`)

Spec §48: "containerized services, managed PostgreSQL, Redis, object
storage, CI/CD." This is the concrete version of that sentence: ECS
Fargate (containerized, no EC2 to patch) + RDS Postgres (managed) +
ElastiCache Redis (managed) + S3 (object storage) + an Application Load
Balancer + ECR, all behind a VPC with private subnets for everything except
the ALB itself.

### One-time setup
```bash
cd infrastructure/terraform
terraform init
```

### Build and push the image (do this before `terraform apply` the first
time - `var.api_image` has no default; the ECS task definition needs a
real image to reference)
```bash
aws ecr get-login-password --region af-south-1 | \
  docker login --username AWS --password-stdin <account-id>.dkr.ecr.af-south-1.amazonaws.com
docker build -t farmplatform-api:$(git rev-parse --short HEAD) apps/api
docker tag farmplatform-api:$(git rev-parse --short HEAD) \
  <account-id>.dkr.ecr.af-south-1.amazonaws.com/farmplatform-api:$(git rev-parse --short HEAD)
docker push <account-id>.dkr.ecr.af-south-1.amazonaws.com/farmplatform-api:$(git rev-parse --short HEAD)
```
(The ECR repository itself is created by Terraform - `terraform apply` once
with a placeholder image tag to create `aws_ecr_repository.api` first, push
a real image to it, then `terraform apply` again with the real tag. This
chicken-and-egg step is normal for ECR + Terraform and isn't specific to
this app.)

### Apply
```bash
cp terraform.tfvars.example terraform.tfvars   # then fill in real values - NEVER commit this file
terraform plan
terraform apply
```

`db_password` and `jwt_secret` have no defaults on purpose (spec §49: never
commit secrets) - supply them via `terraform.tfvars` (gitignored) or
`TF_VAR_db_password`/`TF_VAR_jwt_secret` environment variables in CI.

### After apply
- Run migrations once against the new RDS instance (the Terraform ECS task
  definition does not run `alembic upgrade head` automatically the way
  docker-compose and the Kubernetes manifests below do - add an ECS
  scheduled task or a one-off `aws ecs run-task` invoking
  `alembic upgrade head` as part of your actual release process before
  routing traffic to a new task definition revision).
- Point DNS at the `alb_dns_name` output (or the ACM-validated
  `domain_name` you supplied).
- Run the seed script (`scripts/seed.py`) against the new database if you
  want the Phase 1 demo data - do this only in a staging environment, never
  production, per that script's own comments.

### Region note
`af-south-1` (Cape Town) is the AWS region geographically closest to Kenya
as of this writing - there is currently no AWS region located inside Kenya
itself. Confirm current region availability/pricing before committing to
this, since AWS's region footprint changes over time and this document
doesn't get re-verified against AWS's current state automatically.

## 3. Alternative - Kubernetes (`infrastructure/kubernetes/`)

If you're deploying to an existing Kubernetes cluster instead of ECS
(e.g. EKS, GKE, or a self-managed cluster), these manifests run the API
there instead. They deliberately do **not** run Postgres or Redis inside
the cluster - spec §48's own phrasing ("containerized services, managed
PostgreSQL, Redis") separates the two; point `farmplatform-api-secrets`'
`DATABASE_URL`/`REDIS_URL` at whatever managed Postgres/Redis you're
actually using (RDS/ElastiCache from the Terraform above, or any
equivalent). Self-hosting Postgres/Redis *inside* the cluster via
StatefulSets is a different, larger set of manifests (PersistentVolumeClaims,
backup CronJobs) not attempted here.

```bash
kubectl apply -f infrastructure/kubernetes/00-namespace-config.yaml
# edit the Secret in that file (or create your own out-of-band) with real values first
kubectl apply -f infrastructure/kubernetes/10-api-deployment.yaml
kubectl apply -f infrastructure/kubernetes/20-ingress.yaml
```

The Deployment's `initContainers` entry runs `alembic upgrade head` before
the API container starts - unlike the ECS path above, this one does apply
migrations automatically on every rollout, matching docker-compose's local
behavior.

`apps/web` (the Next.js frontend) has no Kubernetes manifest here -
static/SSR Next.js deployments are commonly handled by a platform-specific
host (Vercel, Netlify, or a separate containerized deployment) rather than
folded into the same manifests as the API, and nothing about this app's
frontend requires Kubernetes specifically. Add a Deployment/Service for it
following the same pattern as `10-api-deployment.yaml` if your target
platform needs one.

## Observability once deployed (spec §47)

- `GET /metrics` (Prometheus exposition format) is live with zero extra
  configuration - point a Prometheus server's scrape config at it.
- Distributed tracing via OpenTelemetry is opt-in: set
  `OTEL_EXPORTER_OTLP_ENDPOINT` (in the ConfigMap, or as an ECS task
  environment variable) to a real collector's OTLP HTTP endpoint. Leaving
  it unset (the default in both the ECS task definition and the Kubernetes
  ConfigMap above) means tracing is simply inactive - nothing errors or
  blocks waiting for a collector that isn't there.
- `/health` (liveness) and `/health/ready` (readiness) are used
  differently by each platform above: ECS's task-level `healthCheck` and
  Kubernetes' `livenessProbe` both use `/health`; the ALB target group and
  Kubernetes' `readinessProbe` both use `/health/ready`. This is
  deliberate, not inconsistent - see `app/main.py`'s docstrings on both
  endpoints for why the split matters.

## CI/CD

`.github/workflows/ci.yml` (pre-existing, from an earlier phase) runs the
test suite on every push. It was **not** modified this session to add the
new dependencies (reportlab, qrcode, prometheus-client,
opentelemetry-api/-sdk/-instrumentation-fastapi/-exporter-otlp-proto-http)
as a separate install step - they're already in `requirements.txt`, which
the workflow already installs from in full, so no CI changes were actually
required. What CI does **not** yet do: build and push the Docker image to
ECR, or run `terraform plan`/`kubectl apply`. Wiring CI to actually deploy
(rather than just test) is real additional scope - a
`docker build && docker push` step plus either a `terraform apply` or
`kubectl apply` step, gated on a protected branch - not attempted here
alongside everything else in this session.
