import os, pathlib as _pl
REPO = _pl.Path(__file__).resolve().parents[2]
OUT = os.environ.get("AUDIT_OUT", str(_pl.Path(__file__).resolve().parent / ".out"))
import ast, json, pathlib, re, collections, sys
ROOT = REPO / "apps" / "api"; APP = ROOT / "app"
routes = json.load(open(OUT + "/be_routes.json")); beclasses = json.load(open(OUT + "/be_classes.json"))
mods = json.load(open(OUT + "/fe_platform_modules.json")); fevocab = json.load(open(OUT + "/fe_vocab.json"))

# ---------------- backend vocabularies
be_sets = []   # (label, set)
def strset(v):
    try: x = ast.literal_eval(v)
    except Exception: return None
    if isinstance(x, dict): x = list(x.keys())
    if isinstance(x, (tuple, list, set, frozenset)) and len(x) >= 2 and all(isinstance(i, str) for i in x): return set(x)
    return None
for p in sorted(APP.rglob("*.py")):
    src = p.read_text(encoding="utf-8", errors="ignore")
    try: tree = ast.parse(src)
    except SyntaxError: continue
    rel = str(p.relative_to(APP))
    for n in tree.body:
        tgt = None; val = None
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name): tgt, val = n.targets[0].id, n.value
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.value is not None: tgt, val = n.target.id, n.value
        if tgt and val is not None:
            v = val
            if isinstance(v, ast.Call) and getattr(v.func, "id", "") in ("frozenset", "set", "tuple", "list") and v.args: v = v.args[0]
            s = strset(ast.unparse(v))
            if s: be_sets.append((f"{rel}:{tgt}", s))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            ann = ast.unparse(node.annotation)
            m = re.search(r"Literal\[(.+?)\]", ann)
            if m:
                vals = re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))
                if len(vals) >= 2: be_sets.append((f"{rel}:{node.target.id} (Literal)", set(vals)))
            if isinstance(node.value, ast.Call):
                for k in node.value.keywords:
                    if k.arg in ("pattern", "regex") and isinstance(k.value, ast.Constant):
                        mm = re.fullmatch(r"\^?\(?([\w|\-]+)\)?\$?", k.value.value)
                        if mm and "|" in mm.group(1): be_sets.append((f"{rel}:{node.target.id} (pattern)", set(mm.group(1).split("|"))))
# derived catalogs (pure-python modules): exec to get computed constants
for cat in ("modules/crops/catalog.py", "modules/livestock/catalog.py"):
    p = APP / cat
    if p.exists():
        ns = {}
        try:
            exec(compile(p.read_text(encoding="utf-8"), str(p), "exec"), ns)
            for k, v in ns.items():
                if k.isupper() and isinstance(v, (tuple, list, set, frozenset, dict)):
                    items = list(v.keys()) if isinstance(v, dict) else list(v)
                    if items and all(isinstance(i, str) for i in items): be_sets.append((f"{cat}:{k} (exec)", set(items)))
        except Exception as e: print("  (could not exec", cat, "->", type(e).__name__, str(e)[:60], ")")
print(f"backend vocabularies collected: {len(be_sets)}")

def best(fe_vals):
    fe = set(fe_vals); out = []
    for label, s in be_sets:
        inter = fe & s
        if len(inter) < 3: continue
        j = len(inter) / len(fe | s)
        if j >= 0.45: out.append((j, label, s))
    out.sort(key=lambda t: -t[0]); return out[:1]

# ---------------- A) every frontend option list vs closest backend vocabulary
print("\n######## A) dropdown / status lists vs backend vocabularies ########")
identical = 0; diffs = []
for s in fevocab:
    b = best(s["values"])
    if not b: continue
    j, label, bs = b[0]; fe = set(s["values"])
    if fe == bs: identical += 1; continue
    diffs.append((s, label, fe - bs, bs - fe, j))
print(f"identical to a backend vocabulary: {identical} | differ: {len(diffs)}")
for s, label, fe_only, be_only, j in diffs:
    loc = f"{s['file'].replace('src/','')}:{s['line']}"
    print(f"\n  {loc}  `{s['name']}` ({s['kind']})  ~  {label}  [similarity {j:.2f}]")
    if fe_only: print(f"     FE offers values the backend doesn't list : {sorted(fe_only)}")
    if be_only: print(f"     backend has values the FE doesn't offer    : {sorted(be_only)}")

# ---------------- B) platform config-driven screens vs backend routes/schemas
def segs(p): return [s for s in p.strip("/").split("/") if s]
def match(fe, method):
    fs = segs(fe)
    for r in routes:
        bs = segs(r["path"])
        if r["method"] == method and len(bs) == len(fs) and all(b.startswith("{") or f == "{}" or f == b for f, b in zip(fs, bs)): return r
def cls(key): return beclasses.get(key)
print("\n######## B) platform-admin config screens vs backend ########")
issues = []
for m in mods:
    slug = m["slug"]
    def chk(label, path, method):
        r = match(path, method) if path else None
        if path and r is None: issues.append(("HIGH", slug, f"{label}: {method} {path} has no matching backend route")); 
        return r
    lr = chk("list", m["listPath"], "GET")
    if lr and lr["response_model"]:
        item = re.search(r"\[(?:\w+\.)?(\w+)\]", lr["response_model"])
        keyc = next((k for k in beclasses if item and k.endswith(":" + item.group(1))), None)
        if keyc:
            names = {f["name"] for f in cls(keyc)["fields"]}
            for col in m["columns"]:
                if col not in names: issues.append(("HIGH", slug, f"table column `{col}` is not a field of {keyc.split(':')[1]} -> empty column"))
    cr = chk("create", m["createPath"], "POST")
    if cr and cr["body"] and m["fields"]:
        bc = cls(cr["body"]); names = {f["name"] for f in bc["fields"]}; fe_names = {f["name"] for f in m["fields"]}
        for n in sorted(fe_names - names): issues.append(("MED", slug, f"create form field `{n}` isn't in {cr['body'].split(':')[1]} (silently dropped)"))
        for f in bc["fields"]:
            if f["required"] and f["name"] not in fe_names: issues.append(("HIGH", slug, f"create: backend REQUIRES `{f['name']}` but the form has no such field -> every create fails with 422"))
            elif f["required"]:
                ff = next(x for x in m["fields"] if x["name"] == f["name"])
                if not ff["required"]: issues.append(("MED", slug, f"create: `{f['name']}` is required by the backend but the form doesn't mark it required"))
        for ff in m["fields"]:
            if ff["options"] and ff["name"] in names:
                bf = next(x for x in bc["fields"] if x["name"] == ff["name"])
                pass
    ur = chk("edit", m["itemPath"], "PATCH")
    if ur and ur["body"] and m["fields"]:
        names = {f["name"] for f in cls(ur["body"])["fields"]}
        edit_names = {f["name"] for f in m["fields"] if not f.get("createOnly")} | {f["name"] for f in (m["editExtra"] or [])}
        for n in sorted(edit_names - names): issues.append(("MED", slug, f"edit form field `{n}` isn't accepted by {ur['body'].split(':')[1]} (create-only field offered in edit form -> ignored)"))
    if m["status"]:
        sr = chk("status", m["status"]["path"], m["status"].get("method", "PATCH"))
        if sr and sr["body"]:
            names = {f["name"] for f in cls(sr["body"])["fields"]}
            if m["status"]["field"] not in names: issues.append(("HIGH", slug, f"status body key `{m['status']['field']}` not in {sr['body'].split(':')[1]} ({sorted(names)})"))
        b = best(m["status"]["options"])
        if b and set(m["status"]["options"]) != b[0][2]:
            fe, bs = set(m["status"]["options"]), b[0][2]
            issues.append(("MED", slug, f"status options vs `{b[0][1]}`: FE-only {sorted(fe-bs)} | BE-only {sorted(bs-fe)}"))
    if m["simple"]: chk("action", m["simple"]["path"], "POST")
    # select options inside forms
    for f in (m["fields"] or []) + (m["editExtra"] or []):
        if f["options"]:
            b = best(f["options"]) if len(f["options"]) >= 3 else []
            if b and set(f["options"]) != b[0][2]:
                fe, bs = set(f["options"]), b[0][2]
                issues.append(("MED", slug, f"`{f['name']}` options vs `{b[0][1]}`: FE-only {sorted(fe-bs)} | BE-only {sorted(bs-fe)}"))
order = {"HIGH": 0, "MED": 1}
for sev, slug, msg in sorted(issues, key=lambda t: (order[t[0]], t[1])): print(f"  [{sev}] {slug:16} {msg}")
if not issues: print("  no mismatches")
print(f"\nplatform modules checked: {len(mods)} | issues: {len(issues)}")
_b_failed = any(s == "HIGH" for s, _, _ in issues)


# ---------------- C) frontend permission map (lib/permissions.ts) vs backend
print("\n######## C) admin permission map vs backend ########")
src = (REPO / "apps" / "web" / "src" / "lib" / "permissions.ts").read_text(encoding="utf-8")
pmap = [(m.group(1), None if m.group(2) == "null" else m.group(2).strip('"')) for m in re.finditer(r'\{ prefix: "([^"]+)", permission: (null|"[^"]+") \}', src)]
bep = json.load(open(OUT + "/be_perms.json")); catalog = set(bep["catalog"])
calls_all = json.load(open(OUT + "/fe_calls.json"))
def _m(fe, method):
    fs = segs(fe)
    for r in routes:
        bs = segs(r["path"])
        if r["method"] == method and len(bs) == len(fs) and all(b.startswith("{") or f == "{}" or f == b for f, b in zip(fs, bs)): return r
perm_issues = []
if not catalog: perm_issues.append(("HIGH", "(all)", "backend permission catalog is empty - extraction failed"))
for prefix, perm in pmap:
    if perm and perm not in catalog: perm_issues.append(("HIGH", prefix, f"`{perm}` is not a permission the backend defines"))
    section = prefix.split("/")[2]
    needed = set(); login_only = False
    is_subpage = prefix.count("/") > 2          # e.g. /admin/crops/new: judged on that folder's calls, writes included
    folder = "src/app/admin/" + "/".join(prefix.split("/")[2:]) + "/"
    for c in calls_all:
        in_scope = c["file"].replace("\\", "/").startswith(folder) if is_subpage else (c["file"].replace("\\", "/").startswith(f"src/app/admin/{section}/") and c["method"] == "GET")
        if in_scope and c["path"].startswith("/api/"):
            r = _m(c["path"], c["method"] if c["helper"] != "apiUpload" else "POST")
            if not r: continue
            ps = [p for p in r["perms"] if re.fullmatch(r"[a-z_]+\.[a-z_]+", p)]
            if ps: needed.update(ps)
            else: login_only = True
    if perm and needed and perm not in needed: perm_issues.append(("HIGH", prefix, f"map says `{perm}` but the page's own data loads need {sorted(needed)}"))
    if perm is None and needed: perm_issues.append(("MED", prefix, f"map allows everyone but the page's data loads need {sorted(needed)} -> 403s for roles lacking them"))
    if perm and not needed and not login_only and section not in ("reports",): perm_issues.append(("LOW", prefix, f"`{perm}` could not be cross-checked (page makes no GET calls)"))
for sev, prefix, msg in sorted(perm_issues): print(f"  [{sev}] {prefix:26} {msg}")
print(f"  sections mapped: {len(pmap)} | issues: {len(perm_issues)}")

# ---------------- E) tenant edit forms (lib/edit-configs.ts) vs backend *Update schemas; can("...") permission codes
print("\n######## E) edit forms + permission codes in the UI vs backend ########")
edit_cfg = json.load(open(OUT + "/fe_edit_configs.json")); e_issues = []
KIND = {"text": {"string"}, "textarea": {"string"}, "email": {"string"}, "date": {"string"}, "select": {"string"}, "number": {"number", "string"}, "integer": {"number"}, "checkbox": {"boolean"}}
import ast as _ast
def _base(ann):
    kinds = set()
    for tok in re.split(r"[|\s]+", ann):
        t = tok.split(".")[-1]
        if t in ("str", "EmailStr", "date", "datetime", "UUID"): kinds.add("string")
        elif t == "Decimal": kinds |= {"number", "string"}   # Pydantic accepts a JSON number or a numeric string
        elif t in ("int", "float"): kinds.add("number")
        elif t == "bool": kinds.add("boolean")
    return kinds
for entity, cfg in edit_cfg.items():
    r = _m(cfg["path"], "PATCH")
    if not r or not r["body"]: e_issues.append(("HIGH", entity, f"no PATCH route (or no body model) matches {cfg['path']}")); continue
    bf = {f["name"]: f for f in beclasses[r["body"]]["fields"]}
    for f in cfg["fields"]:
        b = bf.get(f["name"])
        if not b: e_issues.append(("HIGH", entity, f"form field `{f['name']}` is not accepted by {r['body'].split(':')[1]} (the edit would be silently ignored)")); continue
        bk = _base(b["ann"])
        if bk and not (KIND[f["type"]] & bk): e_issues.append(("HIGH", entity, f"`{f['name']}`: form type `{f['type']}` vs backend `{b['ann']}`"))
        if f["options"]:
            hit = best(f["options"]) if len(f["options"]) >= 3 else []
            if hit and set(f["options"]) != hit[0][2]:
                e_issues.append(("HIGH", entity, f"`{f['name']}` options differ from backend `{hit[0][1]}`: FE-only {sorted(set(f['options'])-hit[0][2])} BE-only {sorted(hit[0][2]-set(f['options']))}"))
        if f["required"] and "None" in b["ann"]: pass   # required in the UI (can't be blanked) while nullable server-side is fine
codes_used = collections.defaultdict(list)
for p in (REPO / "apps" / "web" / "src").rglob("*.tsx"):
    _text = p.read_text(encoding="utf-8", errors="ignore")
    for m in re.finditer(r"""\bcan\(["']([a-z_]+\.[a-z_]+)["']\)""", _text): codes_used[m.group(1)].append(p.name)
    for m in re.finditer(r"""<Can permission=["']([a-z_]+\.[a-z_]+)["']""", _text): codes_used[m.group(1)].append(p.name)
for code, files in sorted(codes_used.items()):
    if code not in catalog: e_issues.append(("HIGH", "permissions", f"can(\"{code}\") in {sorted(set(files))} - the backend has no such permission (that button would be hidden from everyone)"))
for sev, who, msg in sorted(e_issues): print(f"  [{sev}] {who:14} {msg}")
print(f"  edit forms checked: {len(edit_cfg)} ({sum(len(c['fields']) for c in edit_cfg.values())} fields) | can() codes checked: {len(codes_used)} | issues: {len(e_issues)}")
if any(s == "HIGH" for s, _, _ in e_issues): _b_failed = True

if _b_failed or any(s == "HIGH" for s, _, _ in perm_issues): sys.exit(1)
