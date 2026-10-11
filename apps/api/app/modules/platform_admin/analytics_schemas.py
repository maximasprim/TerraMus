"""Response shapes for GET /platform/analytics (superadmin charts)."""
import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class LabelCount(BaseModel):
    key: str
    count: int


class TierStat(BaseModel):
    key: str            # tier name
    count: int          # organizations on the tier
    mrr_kes: Decimal    # monthly price x ACTIVE subscriptions on the tier


class MonthlySignups(BaseModel):
    month: str          # YYYY-MM
    count: int          # organizations created that month
    cumulative: int     # all organizations that existed by the end of that month


class MonthlyMoney(BaseModel):
    month: str
    amount: Decimal
    payments: int


class ProviderTotal(BaseModel):
    key: str
    amount: Decimal
    count: int


class TopTenant(BaseModel):
    organization_id: uuid.UUID
    name: str
    is_suspended: bool
    users: int
    animals: int
    crop_plantings: int
    orders: int
    gmv: Decimal        # successful customer payments in the window


class PlatformTotals(BaseModel):
    organizations: int
    users: int
    animals: int
    crop_plantings: int
    orders: int
    mrr_kes: Decimal
    subscription_revenue: Decimal  # collected in the window
    gmv: Decimal                   # tenant sales processed in the window


class PlatformAnalytics(BaseModel):
    start_date: date
    end_date: date
    months: int
    timezone: str
    totals: PlatformTotals
    signups_monthly: list[MonthlySignups]
    organizations_by_status: list[LabelCount]
    organizations_by_tier: list[TierStat]
    subscriptions_by_status: list[LabelCount]
    subscription_revenue_monthly: list[MonthlyMoney]
    tenant_gmv_monthly: list[MonthlyMoney]
    tenant_payments_by_provider: list[ProviderTotal]
    species_distribution: list[LabelCount]
    top_tenants: list[TopTenant]
