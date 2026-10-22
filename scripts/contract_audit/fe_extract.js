const OUT = process.env.AUDIT_OUT || ".";
const ts = require(process.cwd() + "/node_modules/typescript");
const fs = require("fs"), path = require("path");

function walk(d, out = []) {
  for (const e of fs.readdirSync(d, { withFileTypes: true })) {
    const p = path.join(d, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx)$/.test(e.name)) out.push(p);
  }
  return out;
}
const files = walk("src");
const calls = [], types = {};
const HELPERS = new Set(["apiFetch", "platformApiFetch", "apiFetchAll", "platformApiFetchAll", "apiDownload", "apiUpload", "fetch"]);

function litUnion(t, sf) { return t.getText(sf); }
function fieldsOfTypeLiteral(tl, sf) {
  const out = [];
  for (const m of tl.members) if (ts.isPropertySignature(m) && m.name) out.push({ name: m.name.getText(sf).replace(/['"]/g, ""), optional: !!m.questionToken, type: m.type ? m.type.getText(sf) : "any" });
  return out;
}

for (const file of files) {
  const text = fs.readFileSync(file, "utf8");
  const sf = ts.createSourceFile(file, text, ts.ScriptTarget.Latest, true, file.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const line = (n) => sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;

  // ---- type declarations (interfaces + object type aliases)
  (function collect(n) {
    if (ts.isInterfaceDeclaration(n)) {
      const key = n.name.text;
      const fields = fieldsOfTypeLiteral({ members: n.members }, sf);
      const ext = (n.heritageClauses || []).flatMap((h) => h.types.map((t) => t.expression.getText(sf)));
      (types[key] = types[key] || []).push({ file, fields, extends: ext });
    } else if (ts.isTypeAliasDeclaration(n) && ts.isTypeLiteralNode(n.type)) {
      (types[n.name.text] = types[n.name.text] || []).push({ file, fields: fieldsOfTypeLiteral(n.type, sf), extends: [] });
    } else if (ts.isTypeAliasDeclaration(n)) {
      (types["__alias__" + n.name.text] = types["__alias__" + n.name.text] || []).push({ file, text: n.type.getText(sf) });
    }
    ts.forEachChild(n, collect);
  })(sf);

  // ---- helpers to resolve expressions
  function pathText(expr, scopeNode, depth = 0) {
    if (!expr || depth > 4) return { text: "<dynamic>", query: [] };
    if (ts.isStringLiteralLike(expr)) return split(expr.text);
    if (ts.isTemplateExpression(expr)) {
      let t = expr.head.text, q = [];
      let stopped = false;
      const parts = [expr.head.text];
      for (const sp of expr.templateSpans) {
        const raw = sp.expression.getText(sf);
        const spanIsQuery = /[`"'][?&][A-Za-z_]+=/.test(raw);          // e.g. ${f === "all" ? "" : `?status=${f}`}
        if (!stopped && !spanIsQuery) parts.push("{}");                  // a normal path segment: keep it
        if (!stopped && (spanIsQuery || /^\?/.test(sp.literal.text))) {
          for (const m of raw.matchAll(/[?&]([A-Za-z_]+)=/g)) q.push(m[1]);
          stopped = true;
        }
        if (!stopped) parts.push(sp.literal.text);
        else for (const m of sp.literal.text.matchAll(/[?&]([A-Za-z_]+)=/g)) q.push(m[1]);
      }
      const joined = parts.join("");
      const s = split(joined);
      s.query.push(...q);
      return s;
    }
    if (ts.isBinaryExpression(expr) && expr.operatorToken.kind === ts.SyntaxKind.PlusToken) {
      const a = pathText(expr.left, scopeNode, depth + 1), b = pathText(expr.right, scopeNode, depth + 1);
      return { text: a.text + (b.text === "<dynamic>" ? "{}" : b.text), query: [...a.query, ...b.query] };
    }
    if (ts.isParenthesizedExpression(expr)) return pathText(expr.expression, scopeNode, depth + 1);
    if (ts.isIdentifier(expr)) {
      const init = findVarInit(expr.text, scopeNode);
      if (init) return pathText(init, scopeNode, depth + 1);
    }
    return { text: "<dynamic>", query: [] };
  }
  function split(s) {
    const i = s.indexOf("?");
    const q = [];
    if (i >= 0) for (const m of s.slice(i).matchAll(/[?&]([A-Za-z_]+)=/g)) q.push(m[1]);
    return { text: i >= 0 ? s.slice(0, i) : s, query: q };
  }
  function findVarInit(name, node) {
    for (let n = node; n; n = n.parent) {
      const stmts = n.statements || (n.body && n.body.statements) || [];
      for (const st of stmts) if (ts.isVariableStatement(st)) for (const d of st.declarationList.declarations) if (ts.isIdentifier(d.name) && d.name.text === name && d.initializer) return d.initializer;
    }
    return null;
  }
  function findParam(name, node) {
    for (let n = node; n; n = n.parent) if ((ts.isArrowFunction(n) || ts.isFunctionExpression(n) || ts.isFunctionDeclaration(n)) && n.parameters) for (const p of n.parameters) if (ts.isIdentifier(p.name) && p.name.text === name) return p;
    return null;
  }
  function keysOfObject(o) {
    const keys = []; let spread = false;
    for (const p of o.properties) {
      if (ts.isSpreadAssignment(p)) spread = true;
      else if (p.name) keys.push({ name: p.name.getText(sf).replace(/['"]/g, "") });
    }
    return { keys, spread };
  }
  function analyseBody(bodyExpr, scopeNode) {
    if (!bodyExpr) return { kind: "none" };
    if (ts.isIdentifier(bodyExpr) && bodyExpr.text === "formData") return { kind: "formdata" };
    if (ts.isNewExpression(bodyExpr)) return { kind: "formdata" };
    if (ts.isCallExpression(bodyExpr) && bodyExpr.expression.getText(sf) === "JSON.stringify") {
      let arg = bodyExpr.arguments[0];
      if (!arg) return { kind: "other" };
      while (ts.isParenthesizedExpression(arg) || ts.isAsExpression(arg)) arg = arg.expression;
      if (ts.isObjectLiteralExpression(arg)) return { kind: "inline", ...keysOfObject(arg) };
      if (ts.isIdentifier(arg)) {
        const init = findVarInit(arg.text, scopeNode);
        if (init) { let i = init; while (ts.isParenthesizedExpression(i) || ts.isAsExpression(i) || ts.isSatisfiesExpression?.(i)) i = i.expression; if (ts.isObjectLiteralExpression(i)) return { kind: "var-literal", ...keysOfObject(i) }; }
        const prm = findParam(arg.text, scopeNode);
        if (prm && prm.type) {
          if (ts.isTypeLiteralNode(prm.type)) return { kind: "param-inline", keys: fieldsOfTypeLiteral(prm.type, sf).map((f) => ({ name: f.name, optional: f.optional })), spread: false };
          if (ts.isTypeReferenceNode(prm.type)) return { kind: "param-type", typeName: prm.type.typeName.getText(sf), keys: [], spread: false };
        }
        return { kind: "unresolved", ident: arg.text };
      }
      return { kind: "other" };
    }
    return { kind: "other" };
  }

  (function visit(n) {
    if (ts.isCallExpression(n)) {
      const callee = n.expression;
      const name = ts.isIdentifier(callee) ? callee.text : null;
      if (name && HELPERS.has(name) && n.arguments.length) {
        const first = n.arguments[0];
        const p = pathText(first, n);
        if (name !== "fetch" || /api\/v1/.test(first.getText(sf))) {
          let method = name === "apiUpload" ? "POST" : "GET", bodyExpr = null;
          const opts = name === "apiUpload" ? n.arguments[2] : n.arguments[1];   // apiUpload(path, formData, { method })
          if (!/All$/.test(name) && name !== "apiDownload" && opts && ts.isObjectLiteralExpression(opts)) {
            for (const pr of opts.properties) if (ts.isPropertyAssignment(pr)) {
              const k = pr.name.getText(sf);
              if (k === "method" && ts.isStringLiteralLike(pr.initializer)) method = pr.initializer.text.toUpperCase();
              if (k === "body") bodyExpr = pr.initializer;
            }
          }
          let tx = name === "apiDownload" ? "(download)" : null;
          if (n.typeArguments && n.typeArguments[0]) tx = n.typeArguments[0].getText(sf) + (/AllPages|All$/.test(name) ? "[]" : ""); // apiFetchAll<T> returns T[]
          else if (name !== "apiDownload") {
            // response type declared on the enclosing useQuery<T>() / useMutation<T>() instead
            for (let a = n.parent; a; a = a.parent) {
              if (ts.isCallExpression(a) && ts.isIdentifier(a.expression) && /^use(Query|Mutation|InfiniteQuery|SuspenseQuery)$/.test(a.expression.text) && a.typeArguments && a.typeArguments[0]) { tx = a.typeArguments[0].getText(sf); break; }
            }
          }
          const fnName = (() => { for (let a = n.parent; a; a = a.parent) if (ts.isFunctionDeclaration(a) && a.name) return a.name.text; return ""; })();
          calls.push({ file, line: line(n), helper: name, method, path: p.text.replace(/\{[^}]*\}/g, "{}"), rawPath: first.getText(sf).slice(0, 140), query: [...new Set(p.query)], generic: tx, body: analyseBody(bodyExpr, n), fn: fnName });
        }
      }
    }
    ts.forEachChild(n, visit);
  })(sf);
}
fs.writeFileSync(OUT + "/fe_calls.json", JSON.stringify(calls, null, 1));
fs.writeFileSync(OUT + "/fe_types.json", JSON.stringify(types, null, 1));
const byHelper = {};
for (const c of calls) byHelper[c.helper] = (byHelper[c.helper] || 0) + 1;
const dyn = calls.filter((c) => c.path.includes("<dynamic>"));
console.log("call sites:", calls.length, byHelper);
console.log("methods:", calls.reduce((a, c) => ((a[c.method] = (a[c.method] || 0) + 1), a), {}));
console.log("unresolvable paths:", dyn.length);
dyn.slice(0, 8).forEach((c) => console.log("  ", c.file + ":" + c.line, c.rawPath));
console.log("type declarations:", Object.keys(types).length);
const bk = calls.filter((c) => c.method !== "GET").reduce((a, c) => ((a[c.body.kind] = (a[c.body.kind] || 0) + 1), a), {});
console.log("mutation body analysis:", bk);
