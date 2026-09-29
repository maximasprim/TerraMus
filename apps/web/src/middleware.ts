import { NextRequest, NextResponse } from "next/server";

/**
 * Runs on every request. Most requests are for THIS app's own domain
 * (localhost in dev, your real domain in prod) and pass through
 * unchanged. Only when the Host header is something else — a tenant's
 * custom domain — does this do anything: ask the backend which org that
 * domain belongs to (only ever a VERIFIED domain, see
 * identity/service.py's get_organization_by_verified_domain), then
 * rewrite the request to that org's /shop/{slug}/... route. The visitor's
 * address bar still shows their own domain — Next.js resolves the
 * request against your existing /shop/[orgSlug] pages internally.
 *
 * Known limitation, stated plainly: this calls the backend on every
 * request to a custom domain, with no caching layer. Fine for correctness
 * and for getting this working at all; a production deployment serving
 * meaningful traffic on custom domains would want to cache the
 * domain → slug lookup (Vercel Edge Config or KV are the natural fit,
 * both queryable from middleware) rather than hitting the API each time.
 * Not built here — flagging it rather than pretending this is
 * production-scale as written.
 */

const APP_HOSTS = new Set(
  (process.env.NEXT_PUBLIC_APP_HOSTS ?? "localhost:3000,localhost")
    .split(",")
    .map((h) => h.trim())
    .filter(Boolean),
);

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function isOwnAppHost(host: string): boolean {
  if (APP_HOSTS.has(host)) return true;
  // Vercel preview deployments (*.vercel.app) are always the app's own
  // domain, never a tenant's custom one.
  if (host.endsWith(".vercel.app")) return true;
  return false;
}

function isAlreadyInternalPath(pathname: string): boolean {
  return (
    pathname.startsWith("/shop/") ||
    pathname.startsWith("/admin") ||
    pathname.startsWith("/platform") ||
    pathname.startsWith("/login") ||
    pathname.startsWith("/reset-password") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/_next") ||
    pathname === "/favicon.ico"
  );
}

export async function middleware(request: NextRequest) {
  const host = request.headers.get("host") ?? "";
  const { pathname } = request.nextUrl;

  if (isOwnAppHost(host) || isAlreadyInternalPath(pathname)) {
    return NextResponse.next();
  }

  // This looks like a tenant's custom domain. Resolve it.
  let slug: string | null = null;
  try {
    const resp = await fetch(`${API_BASE}/api/v1/public/resolve-domain?host=${encodeURIComponent(host)}`);
    if (resp.ok) {
      const data = await resp.json();
      slug = data?.slug ?? null;
    }
  } catch {
    // Backend unreachable — fall through to a normal 404 rather than
    // throwing, so a transient API issue doesn't take down every custom
    // domain's storefront with a hard error.
  }

  if (!slug) {
    // Unknown or unverified domain — let it 404 naturally rather than
    // silently serving something. No rewrite happens.
    return NextResponse.next();
  }

  const url = request.nextUrl.clone();
  url.pathname = `/shop/${slug}${pathname}`;
  return NextResponse.rewrite(url);
}

export const config = {
  // Skip the middleware entirely for static assets and image optimization
  // requests — no reason to pay the resolve-domain round trip for those.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
