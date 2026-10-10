// Mirrors apps/api/app/modules/*/schemas.py exactly - kept hand-written
// rather than codegen'd since the backend is the single source of truth
// and this slice only needs a handful of response shapes.

export interface Organization {
  id: string;
  name: string;
  slug: string;
  currency: string;
  timezone: string;
}

export interface UserMe {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  roles: { id: string; name: string }[];
}

export interface MeResponse {
  user: UserMe;
  organization: Organization;
  permissions: string[];
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface DashboardSummary {
  total_animals: number;
  active_animals: number;
  herd_value: string;
  animals_for_sale: number;
  animals_reserved: number;
  animals_sold: number;
  todays_milk_liters: string;
  inventory_value: string;
  monthly_revenue: string;
  monthly_expenses: string;
  estimated_monthly_profit: string;
  low_stock_item_count: number;
  vaccinations_due_count: number;
  total_crop_plantings: number;
  active_crop_plantings: number;
  crop_planting_value: string;
  low_stock_crop_listing_count: number;
}

export interface Animal {
  id: string;
  organization_id: string;
  farm_id: string;
  location_id: string | null;
  dam_id: string | null;
  sire_id: string | null;
  animal_number: string;
  ear_tag: string | null;
  rfid: string | null;
  species: string;
  breed: string | null;
  category: string | null;
  sex: string;
  name: string | null;
  date_of_birth: string | null;
  acquisition_date: string;
  acquisition_method: string;
  acquisition_cost: string;
  current_value: string | null;
  expected_sale_price: string | null;
  current_weight: string | null;
  target_weight: string | null;
  status: string;
  health_status: string;
  reproductive_status: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface AnimalEvent {
  id: string;
  event_type: string;
  event_at: string;
  data: Record<string, unknown> | null;
  created_at: string;
}

export interface Location {
  id: string;
  branch_id: string;
  name: string;
  location_type: string;
}

export interface Branch {
  id: string;
  farm_id: string;
  name: string;
  locations: Location[];
}

export interface CropPlanting {
  id: string;
  organization_id: string;
  farm_id: string;
  location_id: string | null;
  planting_number: string;
  crop_type: string;
  variety: string | null;
  is_perennial: boolean;
  area_size: string | null;
  area_unit: string;
  planting_date: string;
  planting_method: string | null;
  expected_harvest_date: string | null;
  acquisition_cost: string;
  current_value: string | null;
  expected_yield: string | null;
  yield_unit: string | null;
  status: string;
  health_status: string;
  source: string | null;
  supplier: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface CropEvent {
  id: string;
  event_type: string;
  event_at: string;
  data: Record<string, unknown> | null;
  created_at: string;
}

export interface HarvestRecord {
  id: string;
  quantity: string;
  unit: string;
  quality_grade: string | null;
  harvested_at: string;
  notes: string | null;
  cumulative_yield: string | null;
}

export interface CropPlantingProfitability {
  planting_id: string;
  acquisition_cost: string;
  input_cost: string;
  labor_cost: string;
  other_cost: string;
  total_investment: string;
  total_harvested_value: string | null;
  current_value: string | null;
}

export interface CatalogEntry {
  code: string;
  label: string;
}

export interface SpeciesCatalogEntry extends CatalogEntry {
  suggested_categories: string[];
}

export interface CropTypeCatalogEntry extends CatalogEntry {
  category: string;
  is_perennial: boolean;
  typical_yield_unit: string;
}

export interface EffectiveCatalog {
  livestock_enabled: boolean;
  crops_enabled: boolean;
  species: SpeciesCatalogEntry[];
  crop_types: CropTypeCatalogEntry[];
}

export interface Farm {
  id: string;
  organization_id: string;
  name: string;
  county: string | null;
  address: string | null;
  branches: Branch[];
}

export interface HealthRecord {
  id: string;
  animal_id: string;
  record_type: string;
  title: string;
  description: string | null;
  diagnosis: string | null;
  medication: string | null;
  dosage: string | null;
  administered_by: string | null;
  cost: string | null;
  performed_at: string;
  follow_up_date: string | null;
  follow_up_completed: boolean;
  created_at: string;
}

export interface WeightRecord {
  id: string;
  weight_kg: string;
  recorded_at: string;
  notes: string | null;
  average_daily_gain: string | null;
}

export interface Movement {
  id: string;
  from_location_id: string | null;
  to_location_id: string;
  moved_at: string;
  reason: string | null;
  notes: string | null;
}

export interface Customer {
  id: string;
  organization_id: string;
  name: string;
  phone: string | null;
  email: string | null;
  location: string | null;
  customer_type: string;
  notes: string | null;
  created_at: string;
}

export interface Listing {
  id: string;
  animal_id: string | null;
  crop_planting_id: string | null;
  slug: string;
  title: string;
  description: string | null;
  pricing_type: string;
  price: string | null;
  unit: string | null;
  low_stock_threshold: string | null;
  featured: boolean;
  is_active: boolean;
  created_at: string;
  // photo summary (GET /listings only; absent/0 elsewhere)
  cover_image_id?: string | null;
  cover_thumb_url?: string | null;
  image_count?: number;
}

export interface ListingImage {
  id: string;
  position: number;
  width: number;
  height: number;
  size_bytes: number;
  content_type: string;
  // direct CDN links when the photo lives in a storage bucket (null = served by the API)
  url?: string | null;
  thumb_url?: string | null;
}

export interface Inquiry {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  message: string;
  listing_slug: string | null;
  status: "new" | "read" | "replied" | "archived";
  created_at: string;
}

export interface InquirySummary {
  new: number;
  read: number;
  replied: number;
  archived: number;
}

export interface OrderItem {
  id: string;
  animal_id: string | null;
  crop_planting_id: string | null;
  quantity: string;
  price: string;
}

export interface OrderStatusEvent {
  id: string;
  from_status: string | null;
  to_status: string;
  reason: string | null;
  changed_by: string | null;
  changed_at: string;
}

export interface Order {
  id: string;
  customer_id: string;
  status: string;
  delivery_option: string;
  delivery_address: string | null;
  total_amount: string;
  notes: string | null;
  created_at: string;
  items: OrderItem[];
  status_events: OrderStatusEvent[];
}

export interface InventoryItem {
  id: string;
  organization_id: string;
  farm_id: string | null;
  name: string;
  category: string;
  unit: string;
  reorder_level: string;
  allow_negative_stock: boolean;
  notes: string | null;
  current_stock: string;
}

export interface StockMovement {
  id: string;
  item_id: string;
  movement_type: string;
  quantity: string;
  unit_cost: string | null;
  batch_number: string | null;
  expiry_date: string | null;
  animal_id: string | null;
  reference: string | null;
  notes: string | null;
  moved_at: string;
}

export interface FinanceTransaction {
  id: string;
  transaction_type: string;
  category: string;
  amount: string;
  currency: string;
  reference_type: string | null;
  reference_id: string | null;
  description: string | null;
  transaction_date: string;
  created_at: string;
}

export interface FinanceSummary {
  start_date: string;
  end_date: string;
  total_income: string;
  total_expense: string;
  net_income: string;
  income_by_category: Record<string, string>;
  expense_by_category: Record<string, string>;
}

export interface AnimalProfitabilityDetail {
  animal_id: string;
  animal_number: string;
  species: string;
  status: string;
  acquisition_cost: string;
  feed_cost: string;
  health_cost: string;
  total_investment: string;
  sale_price: string | null;
  expected_sale_price: string | null;
  profit: string | null;
  is_actual: boolean;
}

export interface ProfitabilityReport {
  animals: AnimalProfitabilityDetail[];
  most_profitable: AnimalProfitabilityDetail[];
  least_profitable: AnimalProfitabilityDetail[];
  average_profit: string | null;
}

export interface PregnancyCheck {
  id: string;
  check_date: string;
  result: string;
  notes: string | null;
  created_at: string;
}

export interface BreedingRecord {
  id: string;
  dam_id: string;
  sire_id: string | null;
  sire_external: string | null;
  method: string;
  mating_date: string;
  expected_delivery_date: string | null;
  pregnancy_status: string;
  actual_delivery_date: string | null;
  offspring_count: number | null;
  notes: string | null;
  created_at: string;
  pregnancy_checks: PregnancyCheck[];
}

export interface LactationCycle {
  id: string;
  animal_id: string;
  start_date: string;
  end_date: string | null;
  is_active: boolean;
}

export interface MilkRecord {
  id: string;
  animal_id: string;
  lactation_cycle_id: string | null;
  production_date: string;
  session: string;
  quantity_liters: string;
  rejected: boolean;
  rejection_reason: string | null;
  created_at: string;
}

export interface PublicListing {
  slug: string;
  title: string;
  description: string | null;
  pricing_type: string;
  price: string | null;
  listing_kind: "animal" | "crop_produce";
  featured: boolean;
  county: string | null;
  // animal-only (listing_kind === "animal")
  species: string | null;
  breed: string | null;
  sex: string | null;
  date_of_birth: string | null;
  current_weight: string | null;
  health_status: string | null;
  // crop-only (listing_kind === "crop_produce")
  crop_type: string | null;
  variety: string | null;
  unit: string | null;
  quantity_available: string | null;
  is_perennial: boolean | null;
  // photos, cover first; empty/absent when the farm has not uploaded any
  images?: { id: string; url?: string | null; thumb_url?: string | null }[];
}

export interface PublicFarmProfile {
  farm_name: string;
  tagline: string | null;
  farm_story: string | null;
  logo_url: string | null;
  address: string | null;
  county: string | null;
  phone: string | null;
  email: string | null;
  website: string | null;
  established_year: number | null;
}

export interface PublicOrderConfirmation {
  order_id: string;
  status: string;
  total_amount: string;
  delivery_option: string;
  items: { listing_title: string; quantity: string; price: string }[];
  customer_email: string;
}

export interface PublicTestimonial {
  customer_name: string;
  quote: string;
  rating: number | null;
}

export interface PublicBlogPostSummary {
  slug: string;
  title: string;
  excerpt: string | null;
  cover_image_url: string | null;
  author_name: string | null;
  published_at: string | null;
}

export interface PublicBlogPostDetail extends PublicBlogPostSummary {
  body: string;
  seo_title: string | null;
  seo_description: string | null;
}

export interface PublicFAQ {
  question: string;
  answer: string;
  category: string | null;
}

// --- Procurement (Phase 12) ---

export interface Supplier {
  id: string;
  organization_id: string;
  name: string;
  contact_person: string | null;
  phone: string | null;
  email: string | null;
  address: string | null;
  tax_pin: string | null;
  products_supplied: string | null;
  payment_terms: string | null;
  is_active: boolean;
  notes: string | null;
  created_at: string;
}

export interface PurchaseOrderItem {
  id: string;
  inventory_item_id: string | null;
  description: string;
  quantity: string;
  unit_cost: string;
}

export interface PurchaseOrderStatusEvent {
  from_status: string | null;
  to_status: string;
  reason: string | null;
  changed_by: string | null;
  changed_at: string;
}

export interface PurchaseOrder {
  id: string;
  organization_id: string;
  supplier_id: string;
  po_number: string;
  status: string;
  order_date: string | null;
  expected_delivery_date: string | null;
  notes: string | null;
  requested_by: string | null;
  approved_by: string | null;
  total_amount: string;
  items: PurchaseOrderItem[];
  created_at: string;
}

export interface PurchaseOrderDetail extends PurchaseOrder {
  status_history: PurchaseOrderStatusEvent[];
}

// --- Employees (Phase 13) ---

export interface EmployeeStatusEvent {
  from_status: string | null;
  to_status: string;
  reason: string | null;
  changed_by: string | null;
  changed_at: string;
}

export interface Employee {
  id: string;
  organization_id: string;
  user_id: string | null;
  employee_number: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  department: string | null;
  job_title: string | null;
  employment_type: string;
  employment_status: string;
  assigned_farm_id: string | null;
  assigned_location_id: string | null;
  hire_date: string | null;
  termination_date: string | null;
  notes: string | null;
  created_at: string;
}

export interface EmployeeDetail extends Employee {
  status_history: EmployeeStatusEvent[];
}

export interface WorkShift {
  id: string;
  employee_id: string;
  shift_date: string;
  start_time: string | null;
  end_time: string | null;
  location_id: string | null;
  notes: string | null;
}

// --- Assets (Phase 14) ---

export interface MaintenanceRecord {
  id: string;
  asset_id: string;
  maintenance_type: string;
  maintenance_date: string;
  description: string;
  cost: string | null;
  performed_by: string | null;
  next_due_date: string | null;
}

export interface Asset {
  id: string;
  organization_id: string;
  asset_number: string;
  name: string;
  asset_type: string;
  serial_number: string | null;
  status: string;
  condition: string;
  acquisition_date: string | null;
  acquisition_cost: string | null;
  useful_life_years: number | null;
  salvage_value: string | null;
  warranty_expiry: string | null;
  assigned_farm_id: string | null;
  assigned_location_id: string | null;
  supplier_id: string | null;
  notes: string | null;
  created_at: string;
  current_value: string | null;
  total_maintenance_cost: string;
}

export interface AssetDetail extends Asset {
  maintenance_records: MaintenanceRecord[];
}

// --- Customer accounts (Phase 15) ---

export interface MyAccount {
  user_id: string;
  customer_id: string;
  full_name: string;
  email: string;
  phone: string | null;
  location: string | null;
  customer_type: string;
  created_at: string;
}

export interface MyOrder {
  id: string;
  status: string;
  total_amount: string;
  delivery_option: string | null;
  created_at: string;
  items: { animal_id: string; price: string }[];
}

export interface MyInvoice {
  invoice_number: string;
  subtotal: string;
  tax_amount: string;
  total: string;
  issued_at: string;
}

export interface MyPayment {
  provider: string;
  amount: string;
  status: string;
  initiated_at: string;
  completed_at: string | null;
}

export interface MyOrderDetail extends MyOrder {
  invoice: MyInvoice | null;
  payments: MyPayment[];
}

// --- Search (Phase 18) ---

export interface SearchResult {
  type: string;
  id: string;
  label: string;
  subtitle: string | null;
}

// --- Bulk import (Phase 19) ---

export interface BulkImportResult {
  dry_run: boolean;
  total_rows: number;
  valid_rows: number;
  imported: number;
  errors: { row: number; error: string }[];
}

// --- Inventory valuation (Phase 23) ---

export interface ValuationRow {
  item_id: string;
  item_name: string;
  unit: string;
  quantity_on_hand: string;
  priced_quantity: string;
  avg_unit_cost: string | null;
  total_value: string;
}

// --- Organization settings (Phase 22) ---

export interface OrganizationSettings {
  id: string;
  name: string;
  slug: string;
  currency: string;
  timezone: string;
  invoice_prefix: string;
  po_prefix: string;
  employee_prefix: string;
  asset_prefix: string;
  tax_rate: string;
  default_weight_unit: string;
  default_volume_unit: string;
}

// --- QR / public animal profile (Phase 21) ---

export interface AnimalQRProfile {
  animal_number: string;
  species: string;
  breed: string | null;
  sex: string;
  health_status: string;
  farm_name: string;
  is_for_sale: boolean;
  listing_slug: string | null;
}

// --- Invoices ---

export interface Invoice {
  id: string;
  order_id: string;
  customer_id: string;
  invoice_number: string;
  subtotal: string;
  tax_amount: string;
  total: string;
  issued_at: string;
}

export interface PublicBanner {
  title: string;
  image_url: string;
  link_url: string | null;
}

// --- Roles ---
export interface Role {
  id: string;
  name: string;
}

// --- Reservations ---
export interface Reservation {
  id: string;
  animal_id: string;
  customer_id: string;
  reservation_date: string;
  expiry_date: string;
  deposit_amount: string | null;
  status: string;
  notes: string | null;
  created_at: string;
}

// --- In-app notifications ---
export interface AppNotification {
  id: string;
  category: string;
  title: string;
  body: string;
  related_entity_type: string | null;
  related_entity_id: string | null;
  is_read: boolean;
  created_at: string;
}

// --- CMS ---
export interface FarmProfile {
  farm_name: string;
  tagline: string | null;
  farm_story: string | null;
  logo_url: string | null;
  address: string | null;
  county: string | null;
  phone: string | null;
  email: string | null;
  website: string | null;
  established_year: number | null;
}

export interface Testimonial {
  id: string;
  customer_name: string;
  quote: string;
  rating: number | null;
  is_published: boolean;
  is_featured: boolean;
  sort_order: number;
}

export interface BlogPost {
  id: string;
  slug: string;
  title: string;
  excerpt: string | null;
  body: string;
  cover_image_url: string | null;
  author_name: string | null;
  is_published: boolean;
  published_at: string | null;
  seo_title: string | null;
  seo_description: string | null;
  created_at: string;
}

export interface FAQ {
  id: string;
  question: string;
  answer: string;
  category: string | null;
  sort_order: number;
  is_published: boolean;
}

export interface Banner {
  id: string;
  title: string;
  image_url: string;
  link_url: string | null;
  sort_order: number;
  is_active: boolean;
  starts_at: string | null;
  ends_at: string | null;
}

// --- Profitability report ---
export interface AnimalProfitabilityDetail {
  animal_id: string;
  animal_number: string;
  species: string;
  status: string;
  acquisition_cost: string;
  feed_cost: string;
  health_cost: string;
  total_investment: string;
  sale_price: string | null;
  expected_sale_price: string | null;
  profit: string | null;
  is_actual: boolean;
}

export interface ProfitabilityReport {
  start_date: string | null;
  end_date: string | null;
  animals: AnimalProfitabilityDetail[];
  most_profitable: AnimalProfitabilityDetail[];
  least_profitable: AnimalProfitabilityDetail[];
  average_profit: string | null;
}

export interface PaymentMethod {
  provider: string; // value for /public/{org}/orders/{id}/pay/{provider}
  label: string;
  input: string; // what the customer must supply, e.g. "phone"
}

export interface AuditLogEntry {
  id: string;
  user_id: string | null;
  user_name: string | null; // null for system actions and platform-support staff
  action: string;
  entity_type: string;
  entity_id: string | null;
  previous_value: Record<string, unknown> | null;
  new_value: Record<string, unknown> | null;
  created_at: string;
}
