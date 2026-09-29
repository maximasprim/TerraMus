"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Button, Input, ErrorState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";

/** One page handles both steps of spec §5's "password reset" flow: with no
 * ?token= in the URL it's the request form (spec's own enumeration-safe
 * design means this always shows the same generic success message); with a
 * token present (the link the user's email contains) it's the confirm form.
 * Shared by staff and customer accounts alike - the backend endpoint
 * (POST /api/v1/auth/password-reset/*) doesn't distinguish between them
 * (see apps/api's docs/architecture.md Phase 15 note on why a customer
 * account is just an ordinary User), so there's no reason for two pages. */
export default function ResetPasswordPage() {
  return (
    // useSearchParams() opts a page out of static rendering unless it's
    // wrapped in Suspense - required for `next build`'s static export step
    // to succeed (it was previously unwrapped, which only surfaces as a
    // build-time failure, not a dev-server one - hence going unnoticed).
    <Suspense fallback={null}>
      <ResetPasswordContent />
    </Suspense>
  );
}

function ResetPasswordContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="font-display text-3xl italic text-forest">TerraMus</p>
          <p className="mt-1 text-sm text-muted">
            {token ? "Choose a new password" : "Reset your password"}
          </p>
        </div>
        {token ? <ConfirmForm token={token} /> : <RequestForm />}
      </div>
    </div>
  );
}

function RequestForm() {
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (submitted) {
    return (
      <div className="rounded-lg border border-hairline bg-white/60 p-6 text-sm text-ink">
        If that email is registered, a password reset link has been sent. Check your inbox.
      </div>
    );
  }

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setPending(true);
        setError(null);
        try {
          await apiFetch("/api/v1/auth/password-reset/request", {
            method: "POST", auth: false, body: JSON.stringify({ email }),
          });
          setSubmitted(true);
        } catch (err) {
          setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
        } finally {
          setPending(false);
        }
      }}
      className="space-y-4 rounded-lg border border-hairline bg-white/60 p-6"
    >
      {error && <ErrorState message={error} />}
      <Input id="reset-email" label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Sending…" : "Send reset link"}
      </Button>
      <p className="text-center text-sm">
        <Link href="/login" className="text-forest hover:underline">Back to sign in</Link>
      </p>
    </form>
  );
}

function ConfirmForm({ token }: { token: string }) {
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (done) {
    return (
      <div className="space-y-4 rounded-lg border border-hairline bg-white/60 p-6 text-sm">
        <p className="text-ink">Password updated. You can now log in with your new password.</p>
        <Link href="/login">
          <Button className="w-full">Go to sign in</Button>
        </Link>
      </div>
    );
  }

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setPending(true);
        setError(null);
        try {
          await apiFetch("/api/v1/auth/password-reset/confirm", {
            method: "POST", auth: false, body: JSON.stringify({ token, new_password: password }),
          });
          setDone(true);
        } catch (err) {
          setError(err instanceof ApiError ? err.message : "This link is invalid or has expired.");
        } finally {
          setPending(false);
        }
      }}
      className="space-y-4 rounded-lg border border-hairline bg-white/60 p-6"
    >
      {error && <ErrorState message={error} />}
      <Input
        id="reset-new-password" label="New password" type="password" required minLength={8}
        value={password} onChange={(e) => setPassword(e.target.value)}
      />
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : "Set new password"}
      </Button>
    </form>
  );
}
