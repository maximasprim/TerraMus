This directory is an empty placeholder from spec §62's suggested repo
structure (`/infrastructure/docker`). The actual Dockerfile and
docker-compose config live at `apps/api/Dockerfile` and
`docker-compose.yml` (repo root) instead - colocating the Dockerfile with
the code it builds, and the compose file at the root where `docker compose
up` is actually run from, rather than splitting them into a separate
`infrastructure/docker/` tree that would just add indirection for a
single-service (today) build.

See `docs/deployment.md` for how these are actually used, and
`infrastructure/terraform/` and `infrastructure/kubernetes/` for
production deployment options.
