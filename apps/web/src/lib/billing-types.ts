// Same shapes as lib/platform-types.ts's Subscription* interfaces (both
// mirror apps/api/app/modules/billing/schemas.py) - kept as a separate file
// from lib/types.ts purely to avoid a large diff against an existing file;
// there's no reason these couldn't live in types.ts too.

export interface SubscriptionTierOut {
  id: string;
  name: string;
  slug: string;
  monthly_price_kes: number;
  max_users: number | null;
  max_animals: number | null;
}

export interface SubscriptionOut {
  id: string;
  organization_id: string;
  status: "trialing" | "active" | "past_due" | "cancelled";
  current_period_start: string;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  tier: SubscriptionTierOut;
}

export interface SubscriptionPaymentOut {
  id: string;
  status: "initiated" | "pending" | "successful" | "failed";
  amount: number;
  currency: string;
  provider_reference: string;
  initiated_at: string;
  completed_at: string | null;
}
