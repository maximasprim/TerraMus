"""Fodder alerts for the daily checks: stock that will not last."""
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fodder.service import stock_position


async def low_cover_alerts(db: AsyncSession, org_id, today: date) -> list[tuple[str, str, str]]:
    out = []
    for s in await stock_position(db, org_id, today):
        if not s["is_active"]:
            continue
        if s["balance_kg"] <= 0 and s["issued_last_30d_kg"] > 0:
            out.append((f"fodder:out:{s['product_id']}", "Fodder out of stock",
                        f"{s['name']} has run out. It was being used at about {s['issued_last_30d_kg'] / 30:,.0f} kg a day."))
        elif s["low_cover"]:
            out.append((f"fodder:cover:{s['product_id']}", "Fodder running low",
                        f"{s['name']}: {s['balance_units']:,.0f} {s['unit_label']}s ({s['balance_kg']:,.0f} kg) left, about {s['days_of_cover']:.0f} days at the current rate "
                        f"(reorder level {s['reorder_days']} days)."))
    return out
