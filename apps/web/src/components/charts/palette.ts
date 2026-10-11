/**
 * Chart colours, drawn from the app's own tokens (see tailwind.config.ts and
 * docs/design-notes.md) so charts read as part of the product, not a bolt-on.
 * Categorical colours were picked to stay distinguishable from each other and
 * to keep the brass/clay/moss meanings: money in = green, money out = clay.
 */
export const SEMANTIC = {
  income: "#3F6B4A", // moss
  expense: "#A6432E", // clay
  net: "#B8862B", // brass
  neutral: "#8A8578", // muted
} as const;

export const CATEGORICAL = [
  "#2C4F3E", // forest-light
  "#B8862B", // brass
  "#A6432E", // clay
  "#6F9A7B", // sage
  "#D9A84C", // brass-light
  "#7A5C3E", // umber
  "#4F7F8C", // slate teal
] as const;

export const OTHER_COLOR = "#B7A99A"; // stone - the grouped "Other" slice

export const colorAt = (i: number): string => CATEGORICAL[i % CATEGORICAL.length];

/** A status keeps the same colour in every chart it appears in. Keys are the raw API values. */
export const STATUS_COLORS: Record<string, string> = {
  // animals
  active: "#3F6B4A", for_sale: "#B8862B", reserved: "#D9A84C", sold: "#2C4F3E",
  transferred: "#7A5C3E", deceased: "#A6432E", missing: "#8A8578", quarantined: "#C26A4A", archived: "#B7A99A",
  // orders
  pending: "#D9A84C", payment_pending: "#B8862B", paid: "#3F6B4A", processing: "#6F9A7B",
  ready_for_fulfillment: "#4F7F8C", dispatched: "#2C4F3E", delivered: "#1F3A2E", completed: "#2C4F3E",
  cancelled: "#8A8578", refunded: "#A6432E", partially_refunded: "#C26A4A", failed: "#7A2E1F",
  // crop plantings
  growing: "#3F6B4A", ready_for_harvest: "#B8862B", harvesting: "#D9A84C", harvested: "#2C4F3E", fallow: "#B7A99A",
  // subscriptions & organizations
  trialing: "#D9A84C", past_due: "#A6432E", suspended: "#A6432E",
};
