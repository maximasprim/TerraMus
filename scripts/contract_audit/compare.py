import os, pathlib as _pl
REPO = _pl.Path(__file__).resolve().parents[2]
OUT = os.environ.get("AUDIT_OUT", str(_pl.Path(__file__).resolve().parent / ".out"))
import ast, json, re, sys, collections
calls = json.load(open(OUT + "/fe_calls.json")); fetypes = json.load(open(OUT + "/fe_types.json"))
routes = json.load(open(OUT + "/be_routes.json")); beclasses = json.load(open(OUT + "/be_classes.json"))
extra_calls = []
try: extra_calls = json.load(open(OUT + "/fe_calls_platform_expanded.json"))
except Exception: pass
calls = [c for c in calls if "<dynamic>" not in c["path"]] + extra_calls

# ---------------- frontend type kinds
def split_top(t, sep="|"):
    out, depth, cur = [], 0, ""
    for ch in t:
        if ch in "<([{": depth += 1
        if ch in ">)]}": depth -= 1
        if ch == sep and depth == 0: out.append(cur.strip()); cur = ""
        else: cur += ch
    out.append(cur.strip()); return [x for x in out if x]

def fe_decl(name, prefer_file=None):
    d = fetypes.get(name)
    if not d: return None
    if prefer_file:
        for x in d:
            if x["file"] == prefer_file: return x
    for x in d:
        if x["file"].endswith("lib/types.ts"): return x
    return d[0]

def fe_fields(name, prefer_file=None, seen=None):
    seen = seen or set()
    if name in seen: return []
    seen.add(name); d = fe_decl(name, prefer_file)
    if not d: return []
    out = []
    for b in d.get("extends", []): out += fe_fields(b, prefer_file, seen)
    names = {f["name"] for f in d["fields"]}
    return [f for f in out if f["name"] not in names] + d["fields"]

def fe_kind(text, prefer_file=None, depth=0):
    """-> (set(kinds), nullable). kinds: string number boolean any record array:<k> object:<Name>"""
    kinds, nullable = set(), False
    for m in split_top(text.strip()):
        m = m.strip().strip("()")
        if m in ("null", "undefined"): nullable = True; continue
        if m in ("string",): kinds.add("string")
        elif m == "number": kinds.add("number")
        elif m == "boolean": kinds.add("boolean")
        elif m in ("any", "unknown", "never", "void", "object"): kinds.add("any")
        elif m.startswith(("'", '"', "`")): kinds.add("string")
        elif re.fullmatch(r"-?\d+(\.\d+)?", m): kinds.add("number")
        elif m in ("true", "false"): kinds.add("boolean")
        elif m.endswith("[]"): kinds.add("array:" + ("|".join(sorted(fe_kind(m[:-2], prefer_file, depth+1)[0])) or "any"))
        elif m.startswith("Array<"): kinds.add("array:" + ("|".join(sorted(fe_kind(m[6:-1], prefer_file, depth+1)[0])) or "any"))
        elif m.startswith(("Record<", "{ [", "{[")): kinds.add("record")
        elif m.startswith("{"): kinds.add("record")
        elif re.fullmatch(r"[A-Za-z_]\w*", m):
            if m in fetypes: kinds.add("object:" + m)
            elif ("__alias__" + m) in fetypes and depth < 4:
                k, n = fe_kind(fetypes["__alias__" + m][0]["text"], prefer_file, depth+1); kinds |= k; nullable |= n
            else: kinds.add("any")
        else: kinds.add("any")
    return kinds, nullable

# ---------------- backend annotation kinds
def be_kind(ann, module, depth=0):
    try: node = ast.parse(ann, mode="eval").body
    except Exception: return {"any"}, False
    return _bk(node, module)
def _bk(n, module):
    kinds, nullable = set(), False
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr):
        for side in (n.left, n.right):
            k, nl = _bk(side, module); kinds |= k; nullable |= nl
        return kinds, nullable
    if isinstance(n, ast.Constant):
        if n.value is None: return set(), True
        return {"string" if isinstance(n.value, str) else "number"}, False
    if isinstance(n, ast.Subscript):
        base = ast.unparse(n.value).split(".")[-1]
        sl = n.slice
        if base in ("Optional",): k, _ = _bk(sl, module); return k, True
        if base == "Annotated": el = sl.elts[0] if isinstance(sl, ast.Tuple) else sl; return _bk(el, module)
        if base == "Union":
            for el in (sl.elts if isinstance(sl, ast.Tuple) else [sl]):
                k, nl = _bk(el, module); kinds |= k; nullable |= nl
            return kinds, nullable
        if base in ("list", "List", "set", "Set", "Sequence", "tuple", "Tuple", "frozenset"):
            el = sl.elts[0] if isinstance(sl, ast.Tuple) else sl; k, _ = _bk(el, module)
            return {"array:" + ("|".join(sorted(k)) or "any")}, False
        if base in ("dict", "Dict", "Mapping"): return {"record"}, False
        if base == "Literal":
            els = sl.elts if isinstance(sl, ast.Tuple) else [sl]
            return {"number" if all(isinstance(e, ast.Constant) and isinstance(e.value, (int, float)) and not isinstance(e.value, bool) for e in els) else "string"}, False
        return {"any"}, False
    name = ast.unparse(n); short = name.split(".")[-1]
    if short in ("str", "EmailStr", "UUID", "datetime", "date", "time", "Decimal", "HttpUrl", "AnyHttpUrl", "bytes", "timedelta"): return {"string"}, False
    if short in ("int", "float"): return {"number"}, False
    if short == "bool": return {"boolean"}, False
    if short in ("Any", "object", "dict"): return {"any"}, False
    # class reference?
    for key in ([f"{module}:{short}"] + [k for k in beclasses if k.endswith(":" + short)]):
        if key in beclasses and beclasses[key]["isModel"]: return {"object:" + key}, False
    return {"any"}, False

# ---------------- route matching
def segs(p): return [s for s in p.strip("/").split("/") if s]
def match(fe_path, method):
    fs = segs(fe_path); best = None; other_methods = set()
    for r in routes:
        bs = segs(r["path"])
        if len(bs) != len(fs): continue
        score = 0; ok = True
        for f, b in zip(fs, bs):
            if b.startswith("{"): continue
            if f == "{}": score += 1; continue
            if f != b: ok = False; break
        if not ok: continue
        if r["method"] == method:
            if best is None or score < best[0]: best = (score, r)
        else: other_methods.add(r["method"])
    return (best[1] if best else None), other_methods

issues = collections.defaultdict(list)
def add(sev, cat, where, msg): issues[sev].append((cat, where, msg))

def parse_generic(g):
    g = (g or "").strip()
    if not g or g in ("(download)", "void", "unknown", "any"): return None
    if g.endswith("[]"): return ("list", g[:-2].strip())
    return ("one", g)

def compare_obj(fe_name, be_key, where, depth, prefer_file, seen):
    if depth > 3 or (fe_name, be_key) in seen: return
    seen.add((fe_name, be_key))
    be = beclasses.get(be_key)
    if not be: return
    bef = {f["name"]: f for f in be["fields"]}
    for ff in fe_fields(fe_name, prefer_file):
        b = bef.get(ff["name"])
        if b is None:
            if ff["optional"]: add("LOW", "response", where, f"{fe_name}.{ff['name']}? is optional in FE and never sent by BE ({be_key.split(':')[1]})")
            else: add("HIGH", "response", where, f"{fe_name}.{ff['name']} is expected by the frontend but {be_key.split(':')[1]} has no such field -> undefined at runtime")
            continue
        module = be_key.split(":")[0]
        bk, bnull = be_kind(b["ann"], module); fk, fnull = fe_kind(ff["type"], prefer_file)
        if "any" in bk or "any" in fk: pass
        else:
            def base(k): return {x.split(":")[0] for x in k}
            if not (base(bk) & base(fk)) and not (base(bk) <= {"object", "record"} and base(fk) <= {"object", "record"}):
                add("HIGH", "response", where, f"{fe_name}.{ff['name']}: FE type `{ff['type']}` vs BE `{b['ann']}` (JSON kinds differ)")
        if bnull and not fnull and not ff["optional"] and "any" not in fk:
            add("MED", "response", where, f"{fe_name}.{ff['name']}: BE may send null (`{b['ann']}`) but FE type `{ff['type']}` is non-nullable")
        # recurse
        for k in fk:
            if k.startswith("object:"):
                for bk2 in bk:
                    if bk2.startswith("object:"): compare_obj(k[7:], bk2[7:], where, depth+1, prefer_file, seen)
            if k.startswith("array:"):
                inner_fe = k[6:]
                for bk2 in bk:
                    if bk2.startswith("array:"):
                        ib = bk2[6:]
                        if inner_fe.startswith("object:") and ib.startswith("object:"): compare_obj(inner_fe[7:], ib[7:], where, depth+1, prefer_file, seen)

def rm_class(rm, module):
    if not rm: return None, None
    try: n = ast.parse(rm, mode="eval").body
    except Exception: return None, None
    if isinstance(n, ast.Subscript) and ast.unparse(n.value).split(".")[-1] in ("list", "List"):
        k, _ = _bk(n.slice, module); return "list", [x for x in k if x.startswith("object:")]
    k, _ = _bk(n, module); return "one", [x for x in k if x.startswith("object:")]

stats = collections.Counter(); unmatched = []; unverified_resp = 0; why = collections.Counter()
for c in calls:
    where = f"{c['file'].replace('src/','')}:{c['line']}"
    path = c["path"]
    if not path.startswith("/api/"): continue
    route, other = match(path, c["method"])
    if route is None:
        if other: add("HIGH", "route", where, f"{c['method']} {path} - route exists only for {sorted(other)} (405 at runtime)")
        else: add("HIGH", "route", where, f"{c['method']} {path} - NO matching backend route (404 at runtime)")
        stats["no_route"] += 1; continue
    stats["matched"] += 1
    mod = route["module"]
    # ----- response
    gen = parse_generic(c["generic"])
    if c["helper"] in ("apiFetch", "platformApiFetch", "apiFetchAll", "platformApiFetchAll") and gen and route["response_model"]:
        cont, targets = rm_class(route["response_model"], mod)
        if cont and gen[0] != cont and targets:
            add("HIGH", "response", where, f"{c['method']} {path}: FE expects {'an array' if gen[0]=='list' else 'one object'} (`{c['generic']}`) but BE returns {'a list' if cont=='list' else 'one object'} (`{route['response_model']}`)")
        elif targets and gen[1] in fetypes:
            for t in targets: compare_obj(gen[1], t[7:], f"{where}  {c['method']} {path}", 0, c["file"], set())
            stats["resp_compared"] += 1
        else: unverified_resp += 1; why["BE response is a list/obj my parser can't type, or FE type unknown: " + str(gen[1])[:40]] += 1
    else:
        unverified_resp += 1
        why["no FE generic" if not gen else ("BE route has no response_model" if not route["response_model"] else "other")] += 1
    # ----- request body
    if c["method"] != "GET" and c["body"]["kind"] in ("inline", "var-literal", "param-inline", "param-type"):
        bkind = c["body"]; keys = list(bkind.get("keys", [])); spread = bkind.get("spread", False)
        if bkind["kind"] == "param-type":
            decl = fe_fields(bkind["typeName"], c["file"]); keys = [{"name": f["name"], "optional": f["optional"]} for f in decl]
        if route["body"]:
            be = beclasses.get(route["body"]); 
            if be:
                names = {f["name"] for f in be["fields"]} | {f["alias"] for f in be["fields"] if f.get("alias")}
                sent = {k["name"] for k in keys}
                for k in sorted(sent - names): add("MED", "request", where, f"{c['method']} {path}: FE sends `{k}` but {route['body'].split(':')[1]} has no such field (silently dropped, or 422 if extra=forbid)")
                if not spread and bkind["kind"] != "param-type" or (bkind["kind"] == "param-type" and keys):
                    for f in be["fields"]:
                        if f["required"] and f["name"] not in sent and not spread:
                            add("HIGH", "request", where, f"{c['method']} {path}: BE requires `{f['name']}` ({route['body'].split(':')[1]}) but FE never sends it -> 422")
        else:
            add("MED", "request", where, f"{c['method']} {path}: FE sends a JSON body ({sorted(k['name'] for k in keys)}) but the BE route declares no body model")
    # ----- query params
    if c["query"]:
        accepted = {q["name"] for q in route["query"]}
        for q in c["query"]:
            if q not in accepted: add("MED", "query", where, f"{c['method']} {path}: FE sends query `?{q}=` but the BE route doesn't accept it (ignored -> filter does nothing)")

json.dump({k: v for k, v in issues.items()}, open(OUT + "/issues.json", "w"), indent=1)
print(f"call sites analysed: {len(calls)} | matched to a route: {stats['matched']} | unmatched: {stats['no_route']} | response shapes compared: {stats['resp_compared']} | responses not comparable: {unverified_resp}")
print("why not comparable:", dict(why.most_common(8)))
for sev in ("HIGH", "MED", "LOW"):
    items = issues.get(sev, [])
    print(f"\n===== {sev}: {len(items)} =====")
    seen = set()
    for cat, where, msg in items:
        key = (cat, msg)
        if key in seen: continue
        seen.add(key)
        if sev == "LOW" and len(seen) > 12: continue
        print(f"[{cat}] {where}\n     {msg}")

sys.exit(1 if issues.get("HIGH") else 0)
