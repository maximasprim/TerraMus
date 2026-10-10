"""Frontend <-> backend contract audit.

Parses every API call in apps/web (TypeScript compiler API) and every route /
Pydantic schema in apps/api (Python ast), then reports where they disagree:
missing routes/methods, response fields the UI reads but the API never sends,
JSON-type and nullability mismatches, request bodies missing required fields,
ignored query parameters, and drift between hand-copied dropdown/status lists
and the backend's own vocabularies.

    python scripts/contract_audit/run.py          # from the repo root

Needs Node (uses apps/web/node_modules/typescript) and Python 3.10+. No network,
database or running server. Exit code 1 if any HIGH finding exists (CI-friendly).
"""
import os, pathlib, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / ".out"
OUT.mkdir(exist_ok=True)
env = {**os.environ, "AUDIT_OUT": str(OUT)}
web = ROOT / "apps" / "web"

steps = [
    ("extract frontend API calls + types", ["node", str(HERE / "fe_extract.js")], web),
    ("extract frontend option lists + platform screens", ["node", str(HERE / "fe_vocab.js")], web),
    ("extract backend routes + schemas", [sys.executable, str(HERE / "be_extract.py")], ROOT),
    ("compare calls / responses / requests / queries", [sys.executable, str(HERE / "compare.py")], ROOT),
    ("compare option lists + platform screens", [sys.executable, str(HERE / "audit2.py")], ROOT),
]
worst = 0
for title, cmd, cwd in steps:
    print(f"\n>>> {title}", flush=True)
    code = subprocess.run(cmd, cwd=cwd, env=env).returncode
    worst = max(worst, code)
sys.exit(worst)
