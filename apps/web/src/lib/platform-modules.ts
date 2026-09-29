// One entry per module the platform-admin console can browse into for a
// given org. Two tiers, matching what's actually sensible to expose:
//
// - `fields` present → full CRUD: list + create + edit, via a generic
//   form built from this field list (see platform-resource-browser.tsx).
//   Used for the "master data" modules where the shape is simple and
//   stable: livestock, customers, employees, assets, inventory items,
//   suppliers.
// - `fields` absent → read-only monitoring: list view only, no generic
//   create/edit form. Used for modules that are either workflow-driven
//   rather than simple-record-CRUD (breeding's pregnancy-check/delivery
//   sequence, orders' status machine), computed/aggregate (finance
//   summaries, reporting), or genuinely just need to be visible, not
//   edited, from this console (notifications, CMS content). `statusAction`
//   covers the one-field "change status" case (orders, purchase orders,
//   employees) without needing a full edit form for it.
//
// Every path matches a real endpoint in
// apps/api/app/modules/platform_admin/{router,tenant_crud_router}.py
// exactly - see HOW_TO_APPLY.md for the full endpoint list this was built
// against.

export type FieldType = "text" | "number" | "date" | "boolean" | "select" | "textarea" | "farm_picker" | "location_picker" | "supplier_picker";

export interface ModuleField {
  name: string;
  label: string;
  type: FieldType;
  required?: boolean;
  options?: string[]; // for type: "select"
  hint?: string; // e.g. "(UUID - paste from Farms)" for relational fields
}

export interface ModuleColumn {
  key: string;
  label: string;
  format?: "date" | "currency" | "badge" | "raw";
}

export interface ModuleConfig {
  slug: string;
  label: string;
  listPath: (orgId: string) => string;
  columns: ModuleColumn[];
  fields?: ModuleField[]; // present => full CRUD
  editExtraFields?: ModuleField[]; // fields valid on PATCH but not on create (e.g. status), shown only in the edit form
  createPath?: (orgId: string) => string;
  itemPath?: (orgId: string, id: string) => string; // PATCH target for edit
  statusAction?: { field: string; label: string; options: string[]; path: (orgId: string, id: string) => string };
  /** For a single irreversible-ish POST action with no body, like
   * deactivate_listing - a confirm dialog, not a modal form. */
  simpleAction?: { label: string; confirmText: string; path: (orgId: string, id: string) => string };
  rowHref?: (orgId: string, id: string) => string; // makes rows clickable, linking elsewhere instead of/alongside Edit
}


export const PLATFORM_MODULES: ModuleConfig[] = [
  {
    slug: "livestock",
    label: "Livestock",
    listPath: (org) => `/api/v1/platform/organizations/${org}/livestock`,
    createPath: (org) => `/api/v1/platform/organizations/${org}/livestock`,
    itemPath: (org, id) => `/api/v1/platform/organizations/${org}/livestock/${id}`,
    rowHref: (org, id) => `/platform/organizations/${org}/livestock/${id}`,
    columns: [
      { key: "animal_number", label: "Number" }, { key: "species", label: "Species" },
      { key: "breed", label: "Breed" }, { key: "sex", label: "Sex" }, { key: "status", label: "Status", format: "badge" },
    ],
    fields: [
      { name: "farm_id", label: "Farm", type: "farm_picker", required: true },
      { name: "animal_number", label: "Animal number", type: "text", required: true },
      { name: "species", label: "Species", type: "select", required: true, options: ["cattle", "sheep"] },
      { name: "breed", label: "Breed", type: "text" },
      { name: "sex", label: "Sex", type: "select", required: true, options: ["male", "female"] },
      { name: "acquisition_date", label: "Acquisition date", type: "date", required: true },
      { name: "acquisition_method", label: "Acquisition method", type: "select", required: true, options: ["purchased", "born_on_farm", "transferred_in", "gifted"] },
      { name: "acquisition_cost", label: "Acquisition cost (KES)", type: "number" },
    ],
    // The closest thing to "delete" this product has: there is no hard
    // delete for an animal anywhere (tenant-side either) - herd financial
    // history depends on the row surviving. This is the tenant's own
    // status vocabulary (models.py's ANIMAL_STATUSES), including the two
    // that function as an actual removal: "archived" and "deceased".
    statusAction: {
      field: "status", label: "Change status (incl. archive)",
      options: ["active", "for_sale", "reserved", "sold", "transferred", "deceased", "missing", "quarantined", "archived"],
      path: (org, id) => `/api/v1/platform/organizations/${org}/livestock/${id}/status`,
    },
  },
    {
    slug: "crops",
    label: "Crops",
    listPath: (org) => `/api/v1/platform/organizations/${org}/crops`,
    createPath: (org) => `/api/v1/platform/organizations/${org}/crops`,
    itemPath: (org, id) => `/api/v1/platform/organizations/${org}/crops/${id}`,
    columns: [
      { key: "planting_number", label: "Number" }, { key: "crop_type", label: "Crop type" },
      { key: "variety", label: "Variety" }, { key: "status", label: "Status", format: "badge" },
    ],
    fields: [
      { name: "farm_id", label: "Farm", type: "farm_picker", required: true },
      { name: "location_id", label: "Location", type: "location_picker" },
      { name: "planting_number", label: "Planting number", type: "text", required: true },
      // Mirrors apps/api/app/modules/crops/catalog.py's CROP_TYPE_CODES -
      // kept in sync by hand, same convention as livestock's species list
      // above; the backend catalog is still the source of truth/enforcement.
      { name: "crop_type", label: "Crop type", type: "select", required: true, options: [
        "napier_grass", "rhodes_grass", "lucerne", "desmodium", "boma_rhodes", "oat_hay",
        "tea", "coffee", "avocado", "macadamia", "mango", "banana", "passion_fruit", "sugarcane",
        "french_beans", "snow_peas", "tomatoes", "kale_sukuma_wiki", "onions", "cabbage", "capsicum",
        "maize", "wheat", "rice", "sorghum", "millet",
        "beans", "groundnuts", "soybeans",
        "irish_potato", "sweet_potato", "cassava", "arrowroot",
        "roses", "other_cut_flowers",
      ] },
      { name: "variety", label: "Variety", type: "text", hint: "e.g. \"Hass\" avocado, \"Purple Napier\"" },
      { name: "planting_date", label: "Planting date", type: "date", required: true },
      { name: "planting_method", label: "Planting method", type: "select", options: ["seed", "seedling", "cutting", "grafted", "tissue_culture"] },
      { name: "area_size", label: "Area size", type: "number" },
      { name: "area_unit", label: "Area unit", type: "select", options: ["acres", "hectares"] },
      { name: "expected_harvest_date", label: "Expected harvest date", type: "date" },
      { name: "acquisition_cost", label: "Acquisition/input cost (KES)", type: "number" },
      { name: "source", label: "Source", type: "text" },
      { name: "supplier", label: "Supplier", type: "text" },
      { name: "notes", label: "Notes", type: "textarea" },
    ],
    // Mirrors apps/api/app/modules/crops/models.py's PLANTING_STATUSES /
    // _ALLOWED_TRANSITIONS - same "closest thing to delete" reasoning as
    // livestock above ("failed"/"archived" are the terminal states).
    statusAction: {
      field: "status", label: "Change status",
      options: ["growing", "ready_for_harvest", "harvesting", "harvested", "fallow", "failed", "archived"],
      path: (org, id) => `/api/v1/platform/organizations/${org}/crops/${id}/status`,
    },
  },
  {
    slug: "customers",
    label: "Customers",
    listPath: (org) => `/api/v1/platform/organizations/${org}/customers`,
    createPath: (org) => `/api/v1/platform/organizations/${org}/customers`,
    itemPath: (org, id) => `/api/v1/platform/organizations/${org}/customers/${id}`,
    columns: [
      { key: "name", label: "Name" }, { key: "phone", label: "Phone" },
      { key: "email", label: "Email" }, { key: "customer_type", label: "Type", format: "badge" },
    ],
    fields: [
      { name: "name", label: "Name", type: "text", required: true },
      { name: "phone", label: "Phone", type: "text" },
      { name: "email", label: "Email", type: "text" },
      { name: "location", label: "Location", type: "text" },
      { name: "customer_type", label: "Type", type: "select", options: ["individual", "business"] },
      { name: "notes", label: "Notes", type: "textarea" },
    ],
  },
  {
    slug: "employees",
    label: "Employees",
    listPath: (org) => `/api/v1/platform/organizations/${org}/employees`,
    createPath: (org) => `/api/v1/platform/organizations/${org}/employees`,
    itemPath: (org, id) => `/api/v1/platform/organizations/${org}/employees/${id}`,
    columns: [
      { key: "full_name", label: "Name" }, { key: "job_title", label: "Title" },
      { key: "department", label: "Department" }, { key: "employment_status", label: "Status", format: "badge" },
    ],
    fields: [
      { name: "full_name", label: "Full name", type: "text", required: true },
      { name: "phone", label: "Phone", type: "text" },
      { name: "email", label: "Email", type: "text" },
      { name: "department", label: "Department", type: "text" },
      { name: "job_title", label: "Job title", type: "text" },
      { name: "employment_type", label: "Employment type", type: "select", options: ["full_time", "part_time", "casual", "contract"] },
      { name: "assigned_farm_id", label: "Assigned farm", type: "farm_picker" },
      { name: "assigned_location_id", label: "Assigned location", type: "location_picker" },
      { name: "hire_date", label: "Hire date", type: "date" },
      { name: "notes", label: "Notes", type: "textarea" },
    ],
    statusAction: {
      field: "status", label: "Change employment status",
      options: ["active", "on_leave", "suspended", "terminated"],
      path: (org, id) => `/api/v1/platform/organizations/${org}/employees/${id}/status`,
    },
  },
  {
    slug: "assets",
    label: "Assets",
    listPath: (org) => `/api/v1/platform/organizations/${org}/assets`,
    createPath: (org) => `/api/v1/platform/organizations/${org}/assets`,
    itemPath: (org, id) => `/api/v1/platform/organizations/${org}/assets/${id}`,
    columns: [
      { key: "name", label: "Name" }, { key: "asset_type", label: "Type" },
      { key: "condition", label: "Condition" }, { key: "status", label: "Status", format: "badge" },
    ],
    fields: [
      { name: "name", label: "Name", type: "text", required: true },
      { name: "asset_type", label: "Type", type: "select", required: true, options: ["vehicle", "equipment", "structure", "tool", "other"] },
      { name: "serial_number", label: "Serial number", type: "text" },
      { name: "condition", label: "Condition", type: "select", options: ["excellent", "good", "fair", "poor"] },
      { name: "acquisition_date", label: "Acquisition date", type: "date" },
      { name: "acquisition_cost", label: "Acquisition cost (KES)", type: "number" },
      { name: "assigned_farm_id", label: "Assigned farm", type: "farm_picker" },
      { name: "assigned_location_id", label: "Assigned location", type: "location_picker" },
      { name: "supplier_id", label: "Supplier", type: "supplier_picker" },
      { name: "notes", label: "Notes", type: "textarea" },
    ],
    // status ("disposed" is the closest this has to delete) is only valid
    // on AssetUpdate, not AssetCreate - edit-only, same reasoning as
    // suppliers' is_active above.
    editExtraFields: [
      { name: "status", label: "Status", type: "select", options: ["in_use", "in_storage", "under_maintenance", "disposed"] },
    ],
  },
  {
    slug: "inventory",
    label: "Inventory",
    listPath: (org) => `/api/v1/platform/organizations/${org}/inventory/items`,
    createPath: (org) => `/api/v1/platform/organizations/${org}/inventory/items`,
    columns: [
      { key: "name", label: "Name" }, { key: "category", label: "Category" },
      { key: "unit", label: "Unit" }, { key: "current_stock", label: "On hand" },
    ],
    fields: [
      { name: "name", label: "Name", type: "text", required: true },
      { name: "category", label: "Category", type: "select", required: true, options: ["feed", "medication", "supplies", "equipment", "other"] },
      { name: "unit", label: "Unit (e.g. kg, L, bag)", type: "text", required: true },
      { name: "farm_id", label: "Farm", type: "farm_picker" },
      { name: "reorder_level", label: "Reorder level", type: "number" },
      { name: "notes", label: "Notes", type: "textarea" },
    ],
  },
  {
    slug: "suppliers",
    label: "Suppliers",
    listPath: (org) => `/api/v1/platform/organizations/${org}/procurement/suppliers`,
    createPath: (org) => `/api/v1/platform/organizations/${org}/procurement/suppliers`,
    itemPath: (org, id) => `/api/v1/platform/organizations/${org}/procurement/suppliers/${id}`,
    columns: [
      { key: "name", label: "Name" }, { key: "contact_person", label: "Contact" },
      { key: "phone", label: "Phone" }, { key: "is_active", label: "Active", format: "badge" },
    ],
    fields: [
      { name: "name", label: "Name", type: "text", required: true },
      { name: "contact_person", label: "Contact person", type: "text" },
      { name: "phone", label: "Phone", type: "text" },
      { name: "email", label: "Email", type: "text" },
      { name: "address", label: "Address", type: "textarea" },
      { name: "payment_terms", label: "Payment terms", type: "text" },
      { name: "notes", label: "Notes", type: "textarea" },
    ],
    // is_active is the archive mechanism suppliers actually have -
    // SupplierCreate doesn't accept it (a new supplier is always active),
    // but SupplierUpdate does, so it's edit-only rather than in the
    // shared create/edit field list.
    editExtraFields: [
      { name: "is_active", label: "Active", type: "boolean" },
    ],
  },
  {
    slug: "purchase-orders",
    label: "Purchase orders",
    listPath: (org) => `/api/v1/platform/organizations/${org}/procurement/purchase-orders`,
    columns: [
      { key: "po_number", label: "PO #" }, { key: "supplier_id", label: "Supplier" },
      { key: "status", label: "Status", format: "badge" }, { key: "total_amount", label: "Total", format: "currency" },
    ],
    statusAction: {
      field: "status", label: "Change PO status",
      options: ["draft", "submitted", "approved", "received", "cancelled"],
      path: (org, id) => `/api/v1/platform/organizations/${org}/procurement/purchase-orders/${id}/status`,
    },
  },
  {
    slug: "orders",
    label: "Orders",
    listPath: (org) => `/api/v1/platform/organizations/${org}/commerce/orders`,
    columns: [
      { key: "order_number", label: "Order #" }, { key: "customer_id", label: "Customer" },
      { key: "status", label: "Status", format: "badge" }, { key: "total_amount", label: "Total", format: "currency" },
    ],
    statusAction: {
      field: "status", label: "Change order status",
      options: ["pending", "payment_pending", "paid", "processing", "ready_for_fulfillment", "dispatched", "delivered", "completed", "cancelled"],
      path: (org, id) => `/api/v1/platform/organizations/${org}/commerce/orders/${id}/status`,
    },
  },
  {
    slug: "listings",
    label: "Listings",
    listPath: (org) => `/api/v1/platform/organizations/${org}/commerce/listings`,
    columns: [
      { key: "title", label: "Title" }, { key: "pricing_type", label: "Pricing" },
      { key: "price", label: "Price", format: "currency" }, { key: "is_active", label: "Active", format: "badge" },
    ],
    // The tenant's own way to pull a listing off the market - no separate
    // "delete listing" exists either, this IS the removal mechanism.
    simpleAction: {
      label: "Deactivate",
      confirmText: "Deactivate this listing? It will no longer be visible in the shop.",
      path: (org, id) => `/api/v1/platform/organizations/${org}/commerce/listings/${id}/deactivate`,
    },
  },
  {
    slug: "finance",
    label: "Finance",
    listPath: (org) => `/api/v1/platform/organizations/${org}/finance/transactions`,
    columns: [
      { key: "transaction_date", label: "Date", format: "date" }, { key: "transaction_type", label: "Type" },
      { key: "category", label: "Category" }, { key: "amount", label: "Amount", format: "currency" },
    ],
  },
];

// NOT included here: health, breeding, and dairy records. Every endpoint
// tenant_crud_router.py exposes for those three is per-animal
// (.../livestock/{animal_id}/health, .../lactation-cycles, etc.) - there is
// no flat "every health record in this org" endpoint to point a generic
// per-org list browser at, unlike every module above. Surfacing those
// properly needs a different UI shape (pick an animal first, then see its
// history), not a config entry in this list - see HOW_TO_APPLY.md.

export function getModuleConfig(slug: string): ModuleConfig | undefined {
  return PLATFORM_MODULES.find((m) => m.slug === slug);
}
