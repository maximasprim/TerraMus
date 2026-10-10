/**
 * Fields the tenant "Edit" screens offer for each entity. Each list mirrors the
 * backend's `*Update` schema (PATCH body) - the contract audit
 * (`python scripts/contract_audit/run.py`) verifies every field name here exists
 * on that schema and that dropdown options match the backend's allowed values.
 *
 * Identity/structural fields are deliberately absent: they can't be changed via
 * PATCH (an animal's species, a crop's type, an employee's hire date...), and
 * moving an animal between locations goes through Movements so history is kept.
 */
export type EditFieldType = "text" | "textarea" | "number" | "integer" | "date" | "email" | "select" | "checkbox";

export interface EditField {
  name: string;
  label: string;
  type: EditFieldType;
  /** For type "select": the backend's allowed values. */
  options?: string[];
  /** Can't be cleared (the backend column is NOT NULL). */
  required?: boolean;
  hint?: string;
}

export interface EditConfig {
  noun: string;
  path: (id: string) => string;
  fields: EditField[];
}

export const EDIT_CONFIGS = {
  livestock: {
    noun: "animal",
    path: (id) => `/api/v1/livestock/${id}`,
    fields: [
      { name: "name", label: "Name", type: "text" },
      { name: "ear_tag", label: "Ear tag", type: "text" },
      { name: "rfid", label: "RFID", type: "text" },
      { name: "breed", label: "Breed", type: "text" },
      { name: "category", label: "Category", type: "text" },
      { name: "health_status", label: "Health status", type: "text", hint: "e.g. healthy, under treatment" },
      { name: "reproductive_status", label: "Reproductive status", type: "text" },
      { name: "current_value", label: "Current value (KES)", type: "number" },
      { name: "expected_sale_price", label: "Expected sale price (KES)", type: "number" },
      { name: "target_weight", label: "Target weight (kg)", type: "number" },
      { name: "notes", label: "Notes", type: "textarea" },
    ],
  },
  crops: {
    noun: "planting",
    path: (id) => `/api/v1/crops/${id}`,
    fields: [
      { name: "variety", label: "Variety", type: "text" },
      { name: "health_status", label: "Health status", type: "text" },
      { name: "current_value", label: "Current value (KES)", type: "number" },
      { name: "expected_yield", label: "Expected yield", type: "number" },
      { name: "yield_unit", label: "Yield unit", type: "text", hint: "e.g. kg, bags, crates" },
      { name: "expected_harvest_date", label: "Expected harvest date", type: "date" },
      { name: "notes", label: "Notes", type: "textarea" },
    ],
  },
  assets: {
    noun: "asset",
    path: (id) => `/api/v1/assets/${id}`,
    fields: [
      { name: "name", label: "Name", type: "text", required: true },
      { name: "serial_number", label: "Serial number", type: "text" },
      { name: "condition", label: "Condition", type: "select", options: ["excellent", "good", "fair", "poor", "out_of_service"], required: true },
      { name: "status", label: "Status", type: "select", options: ["in_use", "in_storage", "under_maintenance", "disposed"], required: true },
      { name: "useful_life_years", label: "Useful life (years)", type: "integer" },
      { name: "salvage_value", label: "Salvage value (KES)", type: "number" },
      { name: "warranty_expiry", label: "Warranty expiry", type: "date" },
      { name: "notes", label: "Notes", type: "textarea" },
    ],
  },
  employees: {
    noun: "employee",
    path: (id) => `/api/v1/employees/${id}`,
    fields: [
      { name: "full_name", label: "Full name", type: "text", required: true },
      { name: "phone", label: "Phone", type: "text" },
      { name: "email", label: "Email", type: "email" },
      { name: "department", label: "Department", type: "text" },
      { name: "job_title", label: "Job title", type: "text" },
      { name: "employment_type", label: "Employment type", type: "select", options: ["full_time", "part_time", "casual", "contract"], required: true },
      { name: "notes", label: "Notes", type: "textarea" },
    ],
  },
  suppliers: {
    noun: "supplier",
    path: (id) => `/api/v1/procurement/suppliers/${id}`,
    fields: [
      { name: "name", label: "Name", type: "text", required: true },
      { name: "contact_person", label: "Contact person", type: "text" },
      { name: "phone", label: "Phone", type: "text" },
      { name: "email", label: "Email", type: "email" },
      { name: "address", label: "Address", type: "text" },
      { name: "tax_pin", label: "Tax PIN", type: "text" },
      { name: "products_supplied", label: "Products supplied", type: "textarea" },
      { name: "payment_terms", label: "Payment terms", type: "text" },
      { name: "is_active", label: "Active supplier", type: "checkbox" },
      { name: "notes", label: "Notes", type: "textarea" },
    ],
  },
} satisfies Record<string, EditConfig>;

export type EditEntity = keyof typeof EDIT_CONFIGS;

/**
 * Turns the edited form into a PATCH body containing ONLY what changed:
 * blank clears an optional field (null), numbers are sent as numbers, and a
 * cleared required field is reported instead of being sent.
 * Returns `{ patch, error }` - pure, so it can be unit-tested.
 */
export function buildPatch(
  fields: EditField[],
  initial: Record<string, string | boolean>,
  current: Record<string, string | boolean>,
): { patch: Record<string, unknown>; error: string | null } {
  const patch: Record<string, unknown> = {};
  for (const f of fields) {
    const before = initial[f.name];
    const after = current[f.name];
    if (after === before) continue;
    if (f.type === "checkbox") {
      patch[f.name] = Boolean(after);
      continue;
    }
    const text = String(after).trim();
    if (text === "") {
      if (f.required) return { patch: {}, error: `${f.label} can't be empty.` };
      patch[f.name] = null;
    } else if (f.type === "number") {
      const n = Number(text);
      if (!Number.isFinite(n)) return { patch: {}, error: `${f.label} must be a number.` };
      patch[f.name] = n;
    } else if (f.type === "integer") {
      const n = Number(text);
      if (!Number.isInteger(n)) return { patch: {}, error: `${f.label} must be a whole number.` };
      patch[f.name] = n;
    } else {
      patch[f.name] = text;
    }
  }
  return { patch, error: null };
}

/** Form state for the modal: every field as an editable string (checkbox as boolean). */
export function toFormValues(fields: EditField[], source: Record<string, unknown>): Record<string, string | boolean> {
  return Object.fromEntries(
    fields.map((f) => [f.name, f.type === "checkbox" ? Boolean(source[f.name]) : source[f.name] == null ? "" : String(source[f.name])]),
  );
}
