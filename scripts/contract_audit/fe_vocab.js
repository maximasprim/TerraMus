const OUT = process.env.AUDIT_OUT || ".";
const ts = require(process.cwd() + "/node_modules/typescript");
const fs = require("fs"), path = require("path");
function walk(d, out = []) { for (const e of fs.readdirSync(d, { withFileTypes: true })) { const p = path.join(d, e.name); if (e.isDirectory()) walk(p, out); else if (/\.(ts|tsx)$/.test(e.name)) out.push(p); } return out; }
const sets = [], modules = [], editConfigs = {};
const strs = (arr) => arr.elements.every((e) => ts.isStringLiteralLike(e)) ? arr.elements.map((e) => e.text) : null;
for (const file of walk("src")) {
  const sf = ts.createSourceFile(file, fs.readFileSync(file, "utf8"), ts.ScriptTarget.Latest, true, file.endsWith("x") ? ts.ScriptKind.TSX : ts.ScriptKind.TS);
  const ln = (n) => sf.getLineAndCharacterOfPosition(n.getStart(sf)).line + 1;
  const nameOf = (n) => { const p = n.parent; if (p && (ts.isVariableDeclaration(p) || ts.isPropertyAssignment(p) || ts.isPropertySignature(p)) && p.name) return p.name.getText(sf); if (p && ts.isAsExpression(p)) return nameOf(p); return ""; };
  (function visit(n) {
    if (ts.isArrayLiteralExpression(n) && n.elements.length >= 3) { const v = strs(n); if (v) sets.push({ file, line: ln(n), name: nameOf(n) || "(array)", kind: "array", values: [...new Set(v)] }); }
    if (ts.isObjectLiteralExpression(n) && n.properties.length >= 3 && ts.isVariableDeclaration(n.parent) && n.properties.every((p) => ts.isPropertyAssignment(p) && !ts.isComputedPropertyName(p.name) && !(ts.isArrowFunction(p.initializer) || ts.isFunctionExpression(p.initializer)) && (ts.isStringLiteralLike(p.initializer) || ts.isNumericLiteral(p.initializer) || ts.isObjectLiteralExpression(p.initializer) || ts.isArrayLiteralExpression(p.initializer) || ts.isTemplateLiteral(p.initializer)))) {
      sets.push({ file, line: ln(n), name: nameOf(n), kind: "object-keys", values: n.properties.map((p) => p.name.getText(sf).replace(/['"]/g, "")) });
    }
    if ((ts.isJsxElement(n)) && /^(select|Select)$/.test(n.openingElement.tagName.getText(sf))) {
      const vals = [];
      for (const ch of n.children) if (ts.isJsxElement(ch) && ch.openingElement.tagName.getText(sf) === "option") {
        const a = ch.openingElement.attributes.properties.find((x) => ts.isJsxAttribute(x) && x.name.getText(sf) === "value");
        if (a && a.initializer && ts.isStringLiteral(a.initializer) && a.initializer.text) vals.push(a.initializer.text);
      }
      if (vals.length >= 3) { const lab = n.openingElement.attributes.properties.find((x) => ts.isJsxAttribute(x) && /^(id|label)$/.test(x.name.getText(sf))); sets.push({ file, line: ln(n), name: "<select " + (lab && lab.initializer ? lab.initializer.getText(sf) : "") + ">", kind: "options", values: [...new Set(vals)] }); }
    }
    ts.forEachChild(n, visit);
  })(sf);
  if (file.endsWith("edit-configs.ts")) {
    const arrow = (e) => { const t = e.body.getText(sf); return t.replace(/^`|`$/g, "").replace(/\$\{[^}]*\}/g, "{}"); };
    const prop = (o, k) => o.properties.find((p) => ts.isPropertyAssignment(p) && p.name.getText(sf) === k);
    (function find(n) {
      if (ts.isVariableDeclaration(n) && n.name.getText(sf) === "EDIT_CONFIGS") {
        let obj = n.initializer; while (ts.isSatisfiesExpression(obj) || ts.isAsExpression(obj)) obj = obj.expression;
        for (const p of obj.properties) {
          const cfg = p.initializer, g = (k) => prop(cfg, k).initializer;
          editConfigs[p.name.getText(sf)] = { path: arrow(g("path")), fields: g("fields").elements.map((f) => { const v = (k) => { const x = prop(f, k); return x ? x.initializer : null; };
            return { name: v("name").text, type: v("type").text, required: !!(v("required") && v("required").kind === ts.SyntaxKind.TrueKeyword), options: v("options") ? v("options").elements.map((x) => x.text) : null }; }) };
        }
      }
      ts.forEachChild(n, find);
    })(sf);
  }
  if (file.endsWith("platform-modules.ts")) {
    const arrow = (e) => { if (!e) return null; const body = ts.isArrowFunction(e) ? e.body : null; if (!body) return null; const t = body.getText(sf); return t.replace(/^`|`$/g, "").replace(/\$\{[^}]*\}/g, "{}"); };
    const prop = (o, k) => o.properties.find((p) => ts.isPropertyAssignment(p) && p.name.getText(sf) === k);
    const fieldList = (arr) => arr.elements.map((f) => { const g = (k) => { const p = prop(f, k); return p ? p.initializer : null; };
      return { name: g("name").text, type: g("type").text, required: !!(g("required") && g("required").kind === ts.SyntaxKind.TrueKeyword), createOnly: !!(g("createOnly") && g("createOnly").kind === ts.SyntaxKind.TrueKeyword), options: g("options") ? g("options").elements.map((x) => x.text) : null }; });
    (function find(n) {
      if (ts.isVariableDeclaration(n) && n.name.getText(sf) === "PLATFORM_MODULES") {
        for (const m of n.initializer.elements) {
          const g = (k) => { const p = prop(m, k); return p ? p.initializer : null; };
          const sa = g("statusAction"), si = g("simpleAction");
          modules.push({ slug: g("slug").text, listPath: arrow(g("listPath")), createPath: arrow(g("createPath")), itemPath: arrow(g("itemPath")),
            columns: g("columns").elements.map((c) => prop(c, "key").initializer.text), fields: g("fields") ? fieldList(g("fields")) : null,
            editExtra: g("editExtraFields") ? fieldList(g("editExtraFields")) : null,
            status: sa ? { method: prop(sa, "method") ? prop(sa, "method").initializer.text : "PATCH", field: prop(sa, "field").initializer.text, options: prop(sa, "options").initializer.elements.map((x) => x.text), path: arrow(prop(sa, "path").initializer) } : null,
            simple: si ? { path: arrow(prop(si, "path").initializer) } : null });
        }
      }
      ts.forEachChild(n, find);
    })(sf);
  }
}
fs.writeFileSync(OUT + "/fe_edit_configs.json", JSON.stringify(editConfigs, null, 1));
fs.writeFileSync(OUT + "/fe_vocab.json", JSON.stringify(sets, null, 1)); fs.writeFileSync(OUT + "/fe_platform_modules.json", JSON.stringify(modules, null, 1));
console.log("FE vocab sets:", sets.length, "| platform modules:", modules.length, modules.map((m) => m.slug).join(", "));
