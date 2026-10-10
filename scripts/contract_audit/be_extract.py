import os, pathlib as _pl
REPO = _pl.Path(__file__).resolve().parents[2]
OUT = os.environ.get("AUDIT_OUT", str(_pl.Path(__file__).resolve().parent / ".out"))
import ast, json, pathlib, re, sys
ROOT = REPO / "apps" / "api"
APP = ROOT / "app"

def modname(p): return ".".join(p.relative_to(ROOT).with_suffix("").parts).replace(".__init__", "")

# ---------- 1. index every class (pydantic schemas etc.)
classes = {}   # (module, name) -> dict
mods = {}
for p in sorted(APP.rglob("*.py")):
    try: tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError: continue
    m = modname(p); mods[m] = (p, tree)
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            bases = [ast.unparse(b) for b in n.bases]
            fields = []; extra = None
            for s in n.body:
                if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name):
                    required = s.value is None
                    alias = None
                    if isinstance(s.value, ast.Call) and getattr(s.value.func, "id", getattr(s.value.func, "attr", "")) == "Field":
                        kws = {k.arg for k in s.value.keywords}
                        first = s.value.args[0] if s.value.args else None
                        has_default = ("default" in kws) or ("default_factory" in kws) or (first is not None and not (isinstance(first, ast.Constant) and first.value is Ellipsis))
                        required = not has_default
                        for k in s.value.keywords:
                            if k.arg in ("alias", "validation_alias", "serialization_alias") and isinstance(k.value, ast.Constant): alias = k.value.value
                    fields.append({"name": s.target.id, "ann": ast.unparse(s.annotation), "required": required, "alias": alias})
                if isinstance(s, ast.Assign) and any(getattr(t, "id", "") == "model_config" for t in s.targets):
                    txt = ast.unparse(s.value)
                    if "forbid" in txt: extra = "forbid"
            classes[(m, n.name)] = {"bases": bases, "fields": fields, "extra": extra, "module": m}

def imports_of(tree):
    amap = {}   # alias -> ("module", dotted) or ("name", module, original)
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:
                full = f"{n.module}.{a.name}"
                if full in mods or any(k.startswith(full + ".") for k in mods): amap[a.asname or a.name] = ("module", full)
                else: amap[a.asname or a.name] = ("name", n.module, a.name)
        elif isinstance(n, ast.Import):
            for a in n.names: amap[a.asname or a.name.split(".")[0]] = ("module", a.name)
    return amap

def resolve_class(expr_text, module):
    """expr like 'schemas.OrderOut' or 'OrderOut' -> (module, name) or None"""
    _, tree = mods[module]; amap = imports_of(tree)
    parts = expr_text.split(".")
    if len(parts) == 2 and parts[0] in amap and amap[parts[0]][0] == "module":
        key = (amap[parts[0]][1], parts[1]); return key if key in classes else None
    if len(parts) == 1:
        if (module, parts[0]) in classes: return (module, parts[0])
        if parts[0] in amap and amap[parts[0]][0] == "name":
            key = (amap[parts[0]][1], amap[parts[0]][2]); return key if key in classes else None
    return None

def all_fields(key, seen=None):
    seen = seen or set()
    if key in seen or key not in classes: return []
    seen.add(key); c = classes[key]; out = []
    for b in c["bases"]:
        bk = resolve_class(b, key[0])
        if bk: out += all_fields(bk, seen)
    names = {f["name"] for f in c["fields"]}
    return [f for f in out if f["name"] not in names] + c["fields"]

def is_model(key, seen=None):
    seen = seen or set()
    if key in seen or key not in classes: return False
    seen.add(key)
    for b in classes[key]["bases"]:
        if b.split(".")[-1] in ("BaseModel", "BaseSettings"): return True
        bk = resolve_class(b, key[0])
        if bk and is_model(bk, seen): return True
    return False

# ---------- 2. routes
routes = []
for m, (p, tree) in mods.items():
    src = p.read_text(encoding="utf-8", errors="ignore")
    if "APIRouter(" not in src and "FastAPI(" not in src: continue
    prefixes = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call):
            fname = getattr(n.value.func, "id", getattr(n.value.func, "attr", ""))
            if fname in ("APIRouter", "FastAPI"):
                pre = ""
                for k in n.value.keywords:
                    if k.arg == "prefix" and isinstance(k.value, ast.Constant): pre = k.value.value
                for t in n.targets:
                    if isinstance(t, ast.Name): prefixes[t.id] = pre
    for fn in [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        for d in fn.decorator_list:
            if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and isinstance(d.func.value, ast.Name)): continue
            rname = d.func.value.id; verb = d.func.attr
            if rname not in prefixes or verb not in ("get", "post", "put", "patch", "delete"): continue
            sub = d.args[0].value if d.args and isinstance(d.args[0], ast.Constant) else ""
            full = (prefixes[rname] + sub) or "/"
            rm = None; sc = None; deps = []
            for k in d.keywords:
                if k.arg == "response_model": rm = ast.unparse(k.value)
                if k.arg == "status_code": sc = ast.unparse(k.value)
                if k.arg == "dependencies": deps = [ast.unparse(e) for e in k.value.elts] if isinstance(k.value, ast.List) else []
            pathparams = set(re.findall(r"\{(\w+)", full))
            body = None; query = []; multipart = False; perms = []
            args = fn.args.args + fn.args.kwonlyargs
            defaults = [None] * (len(fn.args.args) - len(fn.args.defaults)) + list(fn.args.defaults) + list(fn.args.kw_defaults)
            for a, dflt in zip(args, defaults):
                ann = ast.unparse(a.annotation) if a.annotation else ""
                dtxt = ast.unparse(dflt) if dflt is not None else ""
                if dtxt.startswith("Depends("):
                    mm = re.search(r'require_permission\("([^"]+)"', dtxt)
                    if mm: perms.append(mm.group(1))
                    elif "get_current_platform_admin" in dtxt or "require_write_access" in dtxt: perms.append(dtxt)
                    continue
                if a.arg in pathparams: continue
                if dtxt.startswith(("File(", "Form(")) or "UploadFile" in ann: multipart = True; continue
                if dtxt.startswith("Query("):
                    am = re.search(r"alias=['\"]([^'\"]+)['\"]", dtxt)
                    query.append({"name": am.group(1) if am else a.arg, "required": dtxt.startswith("Query(...") or (dtxt == "Query()")}); continue
                if ann in ("Request", "Response", "AsyncSession", "BackgroundTasks"): continue
                key = resolve_class(ann.split("|")[0].strip(), m) if ann else None
                if key and is_model(key): body = f"{key[0]}:{key[1]}"; continue
                if a.arg in ("db", "user", "ctx", "tenant", "admin", "request", "response"): continue
                query.append({"name": a.arg, "required": dflt is None})
            routes.append({"module": m, "method": verb.upper(), "path": full, "fn": fn.name, "response_model": rm, "status": sc, "body": body, "query": query, "multipart": multipart, "perms": perms + deps, "line": fn.lineno})

# main.py direct app routes use `app` prefix handled above (FastAPI())
json.dump(routes, open(OUT + "/be_routes.json", "w"), indent=1)
json.dump({f"{k[0]}:{k[1]}": {"bases": v["bases"], "fields": all_fields(k), "extra": v["extra"], "isModel": is_model(k)} for k, v in classes.items()}, open(OUT + "/be_classes.json", "w"))
print("routes:", len(routes), "| classes:", len(classes), "| pydantic models:", sum(1 for k in classes if is_model(k)))
from collections import Counter
print(Counter(r["method"] for r in routes))
print("no response_model:", sum(1 for r in routes if not r["response_model"]), "(many are 204/actions)")
print("platform routes:", sum(1 for r in routes if r["path"].startswith("/api/v1/platform")))

# Permission catalog + default role grants (pure-python module, safe to exec). audit2.py step C
# and perm_check.js both read this; nothing produced it before, so a clean checkout crashed there.
import runpy
_perm_ns = runpy.run_path(str(_pl.Path(__file__).resolve().parents[2] / "apps" / "api" / "app" / "modules" / "identity" / "permissions.py"))
json.dump({"catalog": [c for c, _ in _perm_ns["PERMISSIONS"]], "roles": _perm_ns["DEFAULT_ROLE_GRANTS"]}, open(OUT + "/be_perms.json", "w"), indent=1)
