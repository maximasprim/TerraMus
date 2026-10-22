"""Pure parser for the Sahara Oasis "Bulls WG Worksheet" (no database access).

Reads: intake-batch sheets ('BATCH n'), sale-batch sheets ('Sales weight Batch n'),
the 'Bull Inventory register', ' PROFITABILITY ' (landed costs), 'Profitability per
Bull' (price per kg) and the costing sheets (CONCENTRATE, HAY, SILAGE -BLENDED,
TOTAL FEEDING COSTS, OPERATIONS COST, LAND USE).

Dates: the source workbook stores dates as `m/d/yy`, so day/month got swapped in
places (e.g. 11/12/2025 read as 12 Nov). Strings are read as dd/mm/yyyy. A real
date cell that is ambiguous (day <= 12) is resolved by checking which reading fits
between its neighbours in the column sequence (and after delivery); every
correction is reported, never silent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from io import BytesIO
from typing import Any

from openpyxl import load_workbook

_DATE_RE = re.compile(r"^\s*(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})\s*$")
_CALC_WORDS = ("gain", "loss", "wg", "overall", "daily", "%", "adg", "total")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def parse_dmy(text: str) -> date | None:
    m = _DATE_RE.match(text or "")
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    y += 2000 if y < 100 else 0
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def date_candidates(v: Any) -> list[date]:
    """[as-typed reading, day/month-swapped reading] (second only if it differs and is valid)."""
    if isinstance(v, str):
        d = parse_dmy(v)
        return [d] if d else []
    if isinstance(v, (datetime, date)):
        d = v.date() if isinstance(v, datetime) else v
        out = [d]
        if d.day <= 12 and d.day != d.month:
            out.append(date(d.year, d.day, d.month))
        return out
    return []


def resolve_between(cands: list[date], lo: date | None, hi: date | None) -> tuple[date | None, bool, bool]:
    """-> (chosen, swapped, unresolved). Prefers the as-typed reading when it fits."""
    if not cands:
        return None, False, False
    valid = [c for c in cands if (lo is None or c >= lo) and (hi is None or c <= hi)]
    if valid:
        return valid[0], valid[0] != cands[0], False
    return cands[0], False, True


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


@dataclass
class IntakeSheet:
    number: int
    sheet: str
    name: str
    delivered_on: date
    source: str | None
    sex_class: str
    head_hint: int | None
    rows: list[dict] = field(default_factory=list)       # {tag, weights:[(date,kg)], entry_weight}
    weigh_dates: list[date] = field(default_factory=list)


@dataclass
class SaleSheet:
    number: int
    sheet: str
    sold_on: date | None
    rows: list[dict] = field(default_factory=list)       # {tag, received_on, entry_weight, sold_on, sale_weight, intake_hint}


@dataclass
class ParsedWorkbook:
    intake: dict[int, IntakeSheet] = field(default_factory=dict)
    sales: dict[int, SaleSheet] = field(default_factory=dict)
    register_sold: dict[str, str] = field(default_factory=dict)      # tag -> '4' | 'culled'
    register_stock: set[str] = field(default_factory=set)
    register_present: bool = False
    batch_costs: dict[int, dict] = field(default_factory=dict)
    sale_prices: dict[int, float] = field(default_factory=dict)
    docs: list[tuple[str, str, dict]] = field(default_factory=list)  # (kind, name, data)
    warnings: list[dict] = field(default_factory=list)
    date_corrections: list[dict] = field(default_factory=list)

    def warn(self, code: str, where: str, message: str, **extra) -> None:
        self.warnings.append({"code": code, "where": where, "message": message, **extra})


# ----------------------------------------------------------------- intake sheets
def _parse_intake(ws, pw: ParsedWorkbook, number: int) -> None:
    title = str(ws["A1"].value or "")
    m = re.search(r"delivered\s+on\s+(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})", title, re.I)
    delivered = parse_dmy("/".join(m.groups())) if m else None
    if not delivered:
        pw.warn("sheet_skipped", ws.title, "Could not read 'Delivered on dd/mm/yyyy' from cell A1; sheet skipped")
        return
    sm = re.search(r"([A-Za-z][A-Za-z ]*?)\s*[-–]\s*(\d+)\s*(steers?|bulls?|heifers?)", title, re.I)
    source = sm.group(1).strip().title() if sm else None
    head_hint = int(sm.group(2)) if sm else None
    low = title.lower()
    sex = "steer" if "steer" in low else "heifer" if "heifer" in low else "bull"

    cols: list[tuple[int, list[date]]] = []
    for c in range(2, ws.max_column + 1):
        v = ws.cell(2, c).value
        if v is None:
            continue
        if isinstance(v, str) and any(k in v.lower() for k in _CALC_WORDS):
            continue
        cands = date_candidates(v)
        if cands:
            cols.append((c, cands))
    resolved: dict[int, date] = {c: cs[0] for c, cs in cols if len(cs) == 1}
    for idx, (c, cs) in enumerate(cols):
        if len(cs) == 1:
            continue
        lo = next((resolved[cc] for cc, _ in reversed(cols[:idx]) if cc in resolved), delivered)
        lo = max(lo, delivered)
        hi = next((resolved[cc] for cc, _ in cols[idx + 1:] if cc in resolved and len(dict(cols)[cc]) == 1), None)
        chosen, swapped, unresolved = resolve_between(cs, lo, hi)
        resolved[c] = chosen
        where = f"{ws.title}!{ws.cell(2, c).coordinate}"
        if swapped:
            pw.date_corrections.append({"where": where, "read_as": cs[0].isoformat(), "corrected_to": chosen.isoformat(),
                                        "reason": "day/month swapped (fits the weigh-date sequence only when swapped)"})
        elif unresolved:
            pw.warn("date_unresolved", where, f"Ambiguous date {cs[0]}; kept as typed")
    sheet = IntakeSheet(number=number, sheet=ws.title, name=f"BATCH {number}", delivered_on=delivered, source=source,
                        sex_class=sex, head_hint=head_hint, weigh_dates=sorted({d for d in resolved.values() if d}))
    first_col = cols[0][0] if cols else None
    for r in range(3, ws.max_row + 1):
        a = ws.cell(r, 1).value
        if isinstance(a, str) and a.strip().upper().startswith("TOTAL"):
            break
        if a is None or isinstance(a, (int, float)):
            continue
        tag = str(a).strip()
        if not tag:
            continue
        weights = []
        for c, _ in cols:
            kg = _num(ws.cell(r, c).value)
            if kg and kg > 0 and resolved.get(c):
                weights.append((resolved[c], kg))
        entry = _num(ws.cell(r, first_col).value) if first_col else None
        sheet.rows.append({"tag": tag, "weights": weights, "entry_weight": entry or (weights[0][1] if weights else None)})
    pw.intake[number] = sheet


# ------------------------------------------------------------------ sales sheets
def _parse_sales(ws, pw: ParsedWorkbook, number: int) -> None:
    hdr = {}
    for c in range(1, min(ws.max_column, 14) + 1):
        v = ws.cell(1, c).value
        if isinstance(v, str):
            t = _norm(v)
            if "animal" in t: hdr["tag"] = c
            elif "received" in t: hdr["recv"] = c
            elif "entry" in t: hdr["entry"] = c
            elif "date sold" in t or t.startswith("sold"): hdr["sold"] = c
            elif "sales weight" in t or "sale weight" in t: hdr["wt"] = c
    if not {"tag", "wt", "sold"} <= hdr.keys():
        pw.warn("sheet_skipped", ws.title, "Sales sheet headers not recognised (need Animal No., Date sold, Sales Weight)")
        return
    sheet = SaleSheet(number=number, sheet=ws.title, sold_on=None)
    for r in range(2, ws.max_row + 1):
        a = ws.cell(r, hdr["tag"]).value
        wt = _num(ws.cell(r, hdr["wt"]).value)
        if isinstance(a, str) and _norm(a).startswith(("batch", "total")):
            continue
        if isinstance(a, (int, float)):
            continue
        if wt is None or wt <= 0:
            continue
        sold_c = date_candidates(ws.cell(r, hdr["sold"]).value)
        recv_c = date_candidates(ws.cell(r, hdr["recv"]).value) if "recv" in hdr else []
        if not sold_c:
            pw.warn("row_skipped", f"{ws.title}!{r}", "Sale row without a readable sold date")
            continue
        tag = str(a).strip() if a is not None else ""
        sheet.rows.append({"tag": tag, "recv_cands": recv_c, "sold_cands": sold_c,
                           "entry_weight": _num(ws.cell(r, hdr["entry"]).value) if "entry" in hdr else None,
                           "sale_weight": wt, "where": f"{ws.title}!A{r}"})
    pw.sales[number] = sheet


# ---------------------------------------------------------------------- register
def _parse_register(ws, pw: ParsedWorkbook) -> None:
    pw.register_present = True
    batch_cols = [c for c in range(1, ws.max_column + 1)
                  if isinstance(ws.cell(2, c).value, str) and _norm(ws.cell(2, c).value).startswith("batch")]
    groups: list[list[int]] = []
    for c in batch_cols:                      # contiguous columns form one section (sold / current stock)
        if groups and c == groups[-1][-1] + 1:
            groups[-1].append(c)
        else:
            groups.append([c])
    for grp in groups:
        heads = [_norm(str(ws.cell(1, c).value)) for c in range(max(grp[0] - 1, 1), grp[-1] + 2) if ws.cell(1, c).value]
        is_stock = any("stock" in h or "current" in h for h in heads)
        for c in grp:
            for r in range(3, ws.max_row + 1):
                v = ws.cell(r, c).value
                if not isinstance(v, str) or not v.strip():
                    continue
                v = v.strip()
                if is_stock:
                    pw.register_stock.add(v)
                else:
                    m = re.match(r"^(?P<tag>.+?)\.{2,}(?P<code>.+)$", v)
                    if m:
                        pw.register_sold[m.group("tag").strip()] = m.group("code").strip().lower()
                    else:
                        pw.warn("register_unparsed", f"{ws.title}!{ws.cell(r, c).coordinate}", f"Could not read '{v}' (expected TAG...N)")


# ----------------------------------------------------------------- cost sheets
def _parse_batch_costs(ws, pw: ParsedWorkbook) -> None:
    cols = {}
    for c in range(1, ws.max_column + 1):
        v = ws.cell(2, c).value
        if isinstance(v, str):
            t = _norm(v)
            if t == "no of bulls": cols["head"] = c
            elif t == "cost": cols["purchase"] = c
            elif t == "transport": cols["transport"] = c
            elif t.startswith("other"): cols["other"] = c
            elif t.startswith("handler"): cols["handlers"] = c
    if len(cols) < 5:
        pw.warn("sheet_skipped", ws.title, "Buying-price table not recognised")
        return
    for r in range(3, ws.max_row + 1):
        a = ws.cell(r, 1).value
        m = re.match(r"^\s*batch\s*(\d+)\s*$", a, re.I) if isinstance(a, str) else None
        if not m:
            continue
        pw.batch_costs[int(m.group(1))] = {
            "head": int(_num(ws.cell(r, cols["head"]).value) or 0),
            "purchase_cost": _num(ws.cell(r, cols["purchase"]).value) or 0.0,
            "transport_cost": _num(ws.cell(r, cols["transport"]).value) or 0.0,
            "other_fees": _num(ws.cell(r, cols["other"]).value) or 0.0,
            "handlers_cost": _num(ws.cell(r, cols["handlers"]).value) or 0.0}


def _parse_prices(ws_formulas, pw: ParsedWorkbook) -> None:
    current, seen = None, {}
    for r in range(1, ws_formulas.max_row + 1):
        d = ws_formulas.cell(r, 4).value
        if isinstance(d, str):
            m = re.match(r"^\s*sales\s*batch\s*(\d+)\s*$", d, re.I)
            if m:
                current = int(m.group(1)); continue
            f = re.match(r"^=B\d+\*(\d+(?:\.\d+)?)$", d.strip())
            if f and current is not None:
                seen.setdefault(current, []).append(float(f.group(1)))
    for n, prices in seen.items():
        mode = max(set(prices), key=prices.count)
        pw.sale_prices[n] = mode
        if len(set(prices)) > 1:
            pw.warn("price_varies", f"Profitability per Bull / Sales Batch {n}", f"Several prices/kg used in one sale batch {sorted(set(prices))}; using {mode}")


def _formula_factor(f: Any, c_val: float | None, d_val: Any) -> tuple[float, float, float | None]:
    """-> (amount, multiply_by, divide_by) so that amount*mult/div == the per-year figure."""
    if isinstance(f, str) and f.startswith("="):
        m = re.match(r"^=C\d+\s*/\s*(\d+(?:\.\d+)?)$", f.strip())
        if m: return c_val or 0.0, 1.0, float(m.group(1))
        m = re.match(r"^=C\d+\s*\*\s*(\d+(?:\.\d+)?)$", f.strip())
        if m: return c_val or 0.0, float(m.group(1)), 1.0
    py = _num(d_val)
    return (py if py is not None else (c_val or 0.0)), 1.0, 1.0


def _parse_budget_blocks(wsf, wsv, pw: ParsedWorkbook, names: list[str], unit_hint: str) -> None:
    """Enterprise budgets: blocks starting at a 'Cost Item | Total Cost | Per Year' header."""
    blocks = []
    for r in range(1, wsf.max_row + 1):
        b, c = wsf.cell(r, 2).value, wsf.cell(r, 3).value
        if isinstance(b, str) and _norm(b) == "cost item" and isinstance(c, str) and _norm(c) == "total cost":
            blocks.append(r)
    for i, hr in enumerate(blocks):
        lines, yield_v, unit_w, r = [], None, None, hr + 1
        title = next((str(wsf.cell(rr, 2).value).strip(" .") for rr in range(hr - 1, max(hr - 12, 0), -1)
                      if isinstance(wsf.cell(rr, 2).value, str) and wsf.cell(rr, 2).value.strip().isupper()
                      and "ASSUMPTION" not in wsf.cell(rr, 2).value.upper()), f"Budget {i + 1}")
        while r <= wsf.max_row:
            b = wsf.cell(r, 2).value
            if isinstance(b, str) and _norm(b).startswith("total yield"):
                yield_v = _num(wsf.cell(r, 4).value)
                nxt = wsf.cell(r + 2, 4).value
                m = re.match(r"^=D\d+/(\d+(?:\.\d+)?)$", str(wsf.cell(r + 2, 4).value or "")) or re.match(r"^=D\d+/(\d+(?:\.\d+)?)$", str(wsf.cell(r + 1, 4).value or ""))
                unit_w = float(m.group(1)) if m else None
                break
            if isinstance(b, str) and b.strip():
                c_val = _num(wsf.cell(r, 3).value)
                amt, mult, div = _formula_factor(wsf.cell(r, 4).value, c_val, wsv.cell(r, 4).value)
                lines.append({"item": b.strip(), "amount": amt, "multiply_by": mult, "divide_by": div})
            r += 1
        if yield_v:
            nice = re.sub(r"\s*\(per acre\)\s*", "", title, flags=re.I).title().replace("Perrenial", "Perennial").strip(" .-")
            data = {"yield_per_year": yield_v, "yield_unit": unit_hint if unit_w else "kg", "lines": lines,
                    "assumptions": [str(wsf.cell(rr, 2).value) for rr in range(hr - 8, hr)
                                    if isinstance(wsf.cell(rr, 2).value, str) and re.match(r"^\d\.", wsf.cell(rr, 2).value.strip())]}
            if unit_w:
                data["unit_weight_kg"] = unit_w
            pw.docs.append(("enterprise_budget", f"{nice} (per acre)", data))


def _parse_blend_acres(wsf, pw: ParsedWorkbook) -> None:
    """Acres per silage crop come from the blend's `=C93*34`-style total-cost formulas."""
    silage = [d for k, n, d in pw.docs if k == "enterprise_budget" and "hay" not in n.lower()]
    for r in range(1, wsf.max_row + 1):
        b = wsf.cell(r, 2).value
        if isinstance(b, str) and _norm(b) == "total cost":
            for d, c in zip(silage, (3, 4, 5)):
                m = re.match(r"^=[A-Z]+\d+\*(\d+(?:\.\d+)?)$", str(wsf.cell(r, c).value or ""))
                if m:
                    d["acres"] = float(m.group(1))
            return


def _parse_recipe(ws, pw: ParsedWorkbook) -> None:
    ings, fixed = [], []
    for r in range(3, ws.max_row + 1):
        a = ws.cell(r, 1).value
        if not isinstance(a, str) or not a.strip():
            continue
        if _norm(a).startswith("total"):
            break
        q, p, tot = _num(ws.cell(r, 2).value), _num(ws.cell(r, 3).value), _num(ws.cell(r, 4).value)
        if q is not None and p is not None:
            ings.append({"name": a.strip(), "quantity_kg": q, "price_per_kg": p})
        elif tot is not None:
            fixed.append({"name": a.strip(), "amount": tot})
    if ings:
        pw.docs.append(("recipe", "Concentrate (1 tonne)", {"ingredients": ings, "fixed_costs": fixed, "batch_kg": 1000}))


def _parse_ration(ws, pw: ParsedWorkbook) -> None:
    stage_cols = [c for c in range(2, 12) if isinstance(ws.cell(4, c).value, str) and ws.cell(4, c).value.strip()]
    feeds = {}
    for r in (5, 6, 7):
        a = ws.cell(r, 1).value
        if isinstance(a, str):
            feeds[a.strip().lower()] = r
    days_rows = [r for r in range(12, 30) if _num(ws.cell(r, 9).value) and isinstance(ws.cell(r, 1).value, str)
                 and not _norm(ws.cell(r, 1).value).startswith("total")]
    stages = []
    for idx, c in enumerate(stage_cols):
        if idx >= len(days_rows):
            break
        stages.append({"label": str(ws.cell(days_rows[idx], 1).value).strip(), "days": int(_num(ws.cell(days_rows[idx], 9).value)),
                       "feeds": {k: _num(ws.cell(r, c).value) or 0.0 for k, r in feeds.items()}})
    if stages:
        pw.docs.append(("ration_plan", "Fattening ration", {
            "stages": stages, "feed_costs": {},
            "cost_links": {"hay": {"kind": "enterprise_budget", "name": next((n for k, n, _ in pw.docs if k == "enterprise_budget" and "hay" in n.lower()), "Hay (per acre)")},
                           "silage": {"kind": "blend", "names": [n for k, n, _ in pw.docs if k == "enterprise_budget" and "hay" not in n.lower()]},
                           "concentrate": {"kind": "recipe", "name": "Concentrate (1 tonne)"}}}))


def _parse_overhead(wsv, wsf, pw: ParsedWorkbook) -> None:
    lines, heads, cycle = [], None, None
    for r in range(1, wsv.max_row + 1):
        f = wsv.cell(r, 6).value
        if isinstance(f, str) and _norm(f) == "number of bulls": heads = _num(wsv.cell(r, 7).value)
        if isinstance(f, str) and _norm(f) == "production cycle": cycle = _num(wsv.cell(r, 7).value)
    start = next((r + 1 for r in range(1, wsv.max_row + 1)
                  if isinstance(wsv.cell(r, 2).value, str) and "behaviour" in _norm(wsv.cell(r, 2).value)), 22)
    for r in range(start, wsv.max_row + 1):
        a, b, c = wsv.cell(r, 1).value, wsv.cell(r, 2).value, _num(wsv.cell(r, 3).value)
        if c is None:   # file written by code (no cached values): follow a simple '=B12' link ourselves
            m = re.match(r"^=B(\d+)$", str(wsf.cell(r, 3).value or "").strip())
            if m:
                c = _num(wsv.cell(int(m.group(1)), 2).value)
        if isinstance(a, str) and isinstance(b, str) and c is not None and not _norm(a).startswith(("subtotal", "total")):
            beh = _norm(b)
            beh = "fixed" if "fixed" in beh else "variable" if beh == "variable" else "step" if "step" in beh else "semi-variable"
            lines.append({"item": a.strip(), "amount": c, "behaviour": beh})
    if lines:
        pw.docs.append(("overhead_pool", "Bull fattening operations (excl. feed production)",
                        {"lines": lines, "heads": heads or 0, "cycle_days": cycle or 0, "rate_mode": "bull_days"}))


def _parse_land(wsv, pw: ParsedWorkbook) -> None:
    sites = [str(wsv.cell(2, c).value).strip() for c in range(2, 5) if isinstance(wsv.cell(2, c).value, str)
             and _norm(wsv.cell(2, c).value) != "total"]
    rows = []
    for r in range(3, wsv.max_row + 1):
        a = wsv.cell(r, 1).value
        if not isinstance(a, str) or _norm(a) == "total":
            continue
        row = {"item": a.strip(), "irrigated": "irrigated" in _norm(str(wsv.cell(r, 5).value or "")) and "not" not in _norm(str(wsv.cell(r, 5).value or ""))}
        for i, s in enumerate(sites):
            row[s] = _num(wsv.cell(r, 2 + i).value) or 0.0
        rows.append(row)
    if rows:
        pw.docs.append(("land_use", "Land use (acres)", {"unit": "acres", "sites": sites, "rows": rows}))


# --------------------------------------------------------------------- entry point
def parse_workbook(content: bytes) -> ParsedWorkbook:
    pw = ParsedWorkbook()
    try:
        wbv = load_workbook(BytesIO(content), data_only=True)
        wbf = load_workbook(BytesIO(content), data_only=False)
    except Exception as e:  # noqa: BLE001 - surfaced to the caller as a 422
        raise ValueError(f"Not a readable .xlsx workbook: {e}") from e
    by_norm = {_norm(n): n for n in wbv.sheetnames}

    def safe(fn, where, *a):
        try:
            fn(*a)
        except Exception as e:  # noqa: BLE001 - one bad sheet must not sink the import
            pw.warn("sheet_error", where, f"{type(e).__name__}: {e}")

    for name in wbv.sheetnames:
        n = _norm(name)
        m_in = re.match(r"^batch\s*(\d+)", n)
        m_sale = re.match(r"^sales\s*weight\s*batch\s*(\d+)", n)
        if m_sale:
            safe(_parse_sales, name, wbv[name], pw, int(m_sale.group(1)))
        elif m_in:
            safe(_parse_intake, name, wbv[name], pw, int(m_in.group(1)))
        elif "inventory register" in n:
            safe(_parse_register, name, wbv[name], pw)
        elif n == "profitability":
            safe(_parse_batch_costs, name, wbv[name], pw)
        elif "profitability per bull" in n:
            safe(_parse_prices, name, wbf[name], pw)
    if "concentrate" in by_norm: safe(_parse_recipe, "CONCENTRATE", wbv[by_norm["concentrate"]], pw)
    if "hay" in by_norm: safe(_parse_budget_blocks, "HAY", wbf[by_norm["hay"]], wbv[by_norm["hay"]], pw, [], "bale")
    for k, v in by_norm.items():
        if k.startswith("silage"):
            safe(_parse_budget_blocks, v, wbf[v], wbv[v], pw, [], "bale")
            safe(_parse_blend_acres, v, wbf[v], pw)
    if "total feeding costs" in by_norm: safe(_parse_ration, "TOTAL FEEDING COSTS", wbv[by_norm["total feeding costs"]], pw)
    if "operations cost" in by_norm: safe(_parse_overhead, "OPERATIONS COST", wbv[by_norm["operations cost"]], wbf[by_norm["operations cost"]], pw)
    if "land use" in by_norm: safe(_parse_land, "LAND USE", wbv[by_norm["land use"]], pw)
    # sale-batch date = most common sold date among its rows (resolved against received dates later)
    return pw
