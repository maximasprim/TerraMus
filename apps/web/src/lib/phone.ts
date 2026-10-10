/**
 * Kenyan mobile-number normalisation for M-Pesa - a TypeScript twin of
 * apps/api/app/core/phone.py (the backend remains the authority and re-checks).
 * Daraja needs 254XXXXXXXXX; people type 0712 345 678, +254 712 345 678, 712345678...
 */
export const PHONE_ERROR = "Enter a valid Kenyan mobile number, like 0712 345 678";

/** Returns the 254XXXXXXXXX form, or null when it isn't a Kenyan mobile number. */
export function normaliseKePhone(raw: string): string | null {
  let digits = (raw ?? "").replace(/[\s\-().]/g, "");
  if (digits.startsWith("+")) digits = digits.slice(1);
  if (!/^\d+$/.test(digits)) return null;
  if (digits.length === 12 && digits.startsWith("254")) {
    /* already in the right shape */
  } else if (digits.length === 10 && digits.startsWith("0")) {
    digits = "254" + digits.slice(1);
  } else if (digits.length === 9 && "17".includes(digits[0])) {
    digits = "254" + digits;
  } else {
    return null;
  }
  return "17".includes(digits[3]) ? digits : null; // Kenyan mobile ranges are 07xx and 01xx
}
