"""Second production cycle workbook: parsing (no database) and per-cycle batch numbering helpers."""
import pathlib
from types import SimpleNamespace as NS

from app.modules.feedlot.batch_scope import existing_by_number, unassigned_by_number
from app.modules.feedlot.worksheet_parse import parse_workbook

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sahara_oasis_second_cycle.xlsx"


def test_second_cycle_workbook_parses_all_batches_and_costs():
    pw = parse_workbook(FIXTURE.read_bytes())
    assert sorted(pw.intake) == [1, 2, 3, 4, 5, 6]
    assert [len(pw.intake[n].rows) for n in range(1, 7)] == [20, 19, 19, 22, 20, 12]
    tags = [r["tag"] for n in pw.intake for r in pw.intake[n].rows]
    assert len(tags) == len(set(tags)) == 112 and tags[0] == "B01" and tags[-1] == "B0112"
    assert str(pw.intake[1].delivered_on) == "2026-09-03" and str(pw.intake[4].delivered_on) == "2026-10-08"
    assert not [w for w in pw.warnings if w["code"] in ("sheet_skipped", "sheet_error")]
    # purchase costs come from the 'BULLS ACQUISATION COST' sheet
    assert pw.batch_costs[1] == {"head": 20, "purchase_cost": 1187500.0, "transport_cost": 0.0, "other_fees": 14200.0, "handlers_cost": 0.0}
    assert sum(c["purchase_cost"] + c["other_fees"] for c in pw.batch_costs.values()) == 6738100.0
    assert sum(c["head"] for c in pw.batch_costs.values()) == 112


def test_cycle_one_style_title_still_parses():
    from openpyxl import Workbook
    from io import BytesIO
    wb = Workbook(); ws = wb.active; ws.title = "BATCH 1"
    ws["A1"] = "BATCH 1 - Isiolo - 30 steers. Delivered on 11/12/2025."
    ws["A2"] = "ANIMAL NO."; ws["B2"] = "12/12/2025"; ws["A3"] = "A01"; ws["B3"] = 200
    buf = BytesIO(); wb.save(buf)
    pw = parse_workbook(buf.getvalue())
    assert str(pw.intake[1].delivered_on) == "2025-12-11" and pw.intake[1].rows[0]["tag"] == "A01"


def _b(num, cycle, created):
    return NS(batch_number=num, production_cycle_id=cycle, created=created)


def test_matching_is_scoped_to_the_selected_cycle():
    c1, c2 = "cycle-1", "cycle-2"
    rows = [_b(1, c1, 1), _b(2, c1, 2), _b(1, c2, 3), _b(1, None, 0)]
    assert existing_by_number(rows, c2)[1].production_cycle_id == c2 and 2 not in existing_by_number(rows, c2)
    assert existing_by_number(rows, "cycle-3") == {}
    legacy = existing_by_number(rows, None)                     # no cycle selected: unassigned wins, as before
    assert legacy[1].production_cycle_id is None and legacy[2].production_cycle_id == c1
    assert list(unassigned_by_number(rows)) == [1]
