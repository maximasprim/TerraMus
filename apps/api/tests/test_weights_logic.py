"""Weights report: daily-gain bands and readiness (pure logic, no database)."""
from datetime import date, timedelta

from app.modules.weights import logic

D = date(2026, 11, 1)


def pts(*pairs):
    return [(D + timedelta(days=d), w) for d, w in pairs]


def test_adg_bands_match_the_owners_thresholds():
    assert logic.adg_band(None) is None
    assert logic.adg_band(1.26) == "excellent" and logic.adg_band(1.25) == "on_target"
    assert logic.adg_band(0.9) == "on_target" and logic.adg_band(0.89) == "approaching_target"
    assert logic.adg_band(0.6) == "approaching_target" and logic.adg_band(0.59) == "below_target"
    assert logic.adg_band(0) == "below_target" and logic.adg_band(-0.3) == "below_target"


def test_one_weight_per_day_last_entry_wins_and_gains_are_per_day():
    p = logic.daily_points([(D, 200.0), (D, 202.0), (D + timedelta(days=10), 212.0)])
    assert p == [(D, 202.0), (D + timedelta(days=10), 212.0)]
    assert logic.overall_adg(p) == 1.0
    assert logic.overall_adg(p[:1]) is None


def test_recent_gain_uses_the_last_30_days_not_the_whole_history():
    p = pts((0, 200), (60, 260), (80, 290))          # slow first, fast lately (1.5/day over the last 20 days)
    assert round(logic.overall_adg(p), 2) == 1.12
    assert round(logic.recent_adg(p), 2) == 1.5
    assert logic.recent_adg(pts((0, 200), (90, 290))) == 1.0      # only two far-apart weighings: use them


def test_ready_nearly_ready_growing_stalled_and_no_target():
    today = D + timedelta(days=20)
    ready = logic.assess(pts((0, 400), (20, 452)), 450, 400, today)
    assert ready["stage"] == "ready" and ready["remaining_kg"] == 0 and ready["progress_pct"] == 100.0

    near = logic.assess(pts((0, 400), (20, 440)), 450, 400, today)        # 2 kg/day, 10 kg to go -> 5 days
    assert near["stage"] == "nearly_ready" and near["days_to_ready"] == 5 and near["est_ready_date"] == (D + timedelta(days=25)).isoformat()
    assert near["adg_band"] == "excellent" and near["progress_pct"] == 80.0

    far = logic.assess(pts((0, 300), (20, 320)), 450, 300, today)          # 1 kg/day, 130 to go
    assert far["stage"] == "growing" and far["days_to_ready"] == 130 and far["adg_band"] == "on_target"

    stalled = logic.assess(pts((0, 300), (20, 295)), 450, 300, today)
    assert stalled["stage"] == "stalled" and stalled["adg_band"] == "below_target" and stalled["est_ready_date"] is None

    assert logic.assess(pts((0, 300), (20, 320)), None, 300, today)["stage"] == "no_target"
    assert logic.assess(pts((0, 300)), 450, 300, today)["stage"] == "needs_weights"
    assert logic.assess([], 450, None, today)["stage"] == "needs_weights"


def test_unhealthy_ready_animals_are_held_back_but_still_shown():
    today = D + timedelta(days=20)
    held = logic.assess(pts((0, 400), (20, 460)), 450, 400, today, healthy=False, hold_note="Health: sick")
    assert held["stage"] == "ready" and held["hold_reason"] == "Health: sick"
    growing = logic.assess(pts((0, 300), (20, 320)), 450, 300, today, healthy=False)
    assert growing["hold_reason"] is None        # only matters once ready / nearly ready


def test_stale_weighing_is_flagged_and_summary_counts():
    a = logic.assess(pts((0, 300), (10, 310)), 450, 300, D + timedelta(days=100))
    assert "stale_weight" in a["flags"]
    s = logic.summarise([a, logic.assess(pts((0, 300), (20, 340)), 450, 300, D + timedelta(days=21))])
    assert s["head"] == 2 and s["avg_adg"] is not None and sum(s["stages"].values()) == 2
