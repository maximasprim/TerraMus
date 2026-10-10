// Mirrors apps/api/app/modules/platform_admin/schemas.py and
// apps/api/app/modules/billing/schemas.py exactly - same hand-written
// convention as lib/types.ts uses for the tenant side.

export interface PlatformAdminOut {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  role: "superadmin" | "viewer";
}

export interface OrganizationSummaryOut {
  id: string;
  name: string;
  slug: string;
  currency: string;
  is_suspended: boolean;
  user_count: number;
  subscription_tier: string | null;
  subscription_status: string | null;
  created_at: string;
}

export interface PlatformDashboardStats {
  total_organizations: number;
  active_organizations: number;
  suspended_organizations: number;
  total_users: number;
  organizations_by_tier: Record<string, number>;
  mrr_kes: number;
  signups_last_30_days: number;
}

export interface SubscriptionTierOut {
  id: string;
  name: string;
  slug: string;
  monthly_price_kes: number;
  max_users: number | null;
  max_animals: number | null;
  max_crop_plantings?: number | null;
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

/** Raw per-organization catalog restrictions set by a platform admin.
 *  `null` for a list means unrestricted; `[]` means nothing is allowed. */
export interface TenantCatalogSettings {
  organization_id: string;
  livestock_enabled: boolean;
  crops_enabled: boolean;
  enabled_species: string[] | null;
  enabled_crop_types: string[] | null;
}

/** PATCH body - omitted fields are left unchanged by the API. */
export interface TenantCatalogSettingsUpdate {
  livestock_enabled?: boolean;
  crops_enabled?: boolean;
  enabled_species?: string[];
  enabled_crop_types?: string[];
  clear_species_restriction?: boolean;
  clear_crop_type_restriction?: boolean;
}
