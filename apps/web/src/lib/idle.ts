// Pure logic for the inactivity sign-out (no React or browser imports, so scripts/idle.test.ts can run it).
// The server is the real gate (a refresh token not used within the limit is refused); this only lets the page
// warn the user and sign out promptly instead of waiting for their next click to fail.

export type IdleState = "active" | "warning" | "expired";

export const WARN_SECONDS = 120;

/** `idleMinutes` of 0 (or missing) means the feature is off. Times are epoch milliseconds. */
export function idleStatus(now: number, lastActivity: number, idleMinutes: number, warnSeconds = WARN_SECONDS): IdleState {
  if (!idleMinutes || idleMinutes <= 0) return "active";
  const left = idleMinutes * 60_000 - (now - lastActivity);
  if (left <= 0) return "expired";
  return left <= warnSeconds * 1000 ? "warning" : "active";
}

export function secondsLeft(now: number, lastActivity: number, idleMinutes: number): number {
  if (!idleMinutes || idleMinutes <= 0) return Infinity;
  return Math.max(0, Math.ceil((idleMinutes * 60_000 - (now - lastActivity)) / 1000));
}

/** How often to refresh the session while the user is active: well inside the limit, never more than every 10 min. */
export function keepAliveEveryMs(idleMinutes: number): number {
  return Math.min(10, Math.max(1, Math.floor(idleMinutes / 3))) * 60_000;
}

export function idleMessage(minutes: number): string {
  if (minutes >= 60 && minutes % 60 === 0) {
    const h = minutes / 60;
    return `You were signed out after ${h} hour${h === 1 ? "" : "s"} of inactivity.`;
  }
  return `You were signed out after ${minutes} minutes of inactivity.`;
}
