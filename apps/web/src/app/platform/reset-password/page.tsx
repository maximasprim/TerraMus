"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Button, Input, ErrorState } from "@/components/ui";
import { platformApiFetch, PlatformApiError } from "@/lib/platform-api";

/** Same one-page-two-steps shape as apps/web/src/app/reset-password/page.tsx,
 * pointed at the platform-admin endpoints
 * (POST /api/v1/platform/auth/password-reset/*) instead of the tenant ones -
 * kept as a separate page rather than parameterizing the existing one since
 * the two flows hit entirely different backend tables (PlatformAdminPasswordResetToken
 * vs PasswordResetToken) and API clients (platform-api.ts vs api.ts). */
export default function PlatformResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <PlatformResetPasswordContent />
    </Suspense>
  );
}

function PlatformResetPasswordContent() {
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="font-display text-3xl italic text-paper">TerraMus Admin</p>
          <p className="mt-1 text-sm text-paper/60">
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
      <div className="rounded-lg border border-hairline bg-paper p-6 text-sm text-ink">
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
          await platformApiFetch("/api/v1/platform/auth/password-reset/request", {
            method: "POST", auth: false, body: JSON.stringify({ email }),
          });
          setSubmitted(true);
        } catch (err) {
          setError(err instanceof PlatformApiError ? err.message : "Something went wrong. Try again.");
        } finally {
          setPending(false);
        }
      }}
      className="space-y-4 rounded-lg border border-hairline bg-paper p-6"
    >
      {error && <ErrorState message={error} />}
      <Input id="preset-email" label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Sending…" : "Send reset link"}
      </Button>
      <p className="text-center text-sm">
        <Link href="/platform/login" className="text-forest hover:underline">Back to sign in</Link>
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
      <div className="space-y-4 rounded-lg border border-hairline bg-paper p-6 text-sm">
        <p className="text-ink">Password updated. You can now log in with your new password.</p>
        <Link href="/platform/login">
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
          await platformApiFetch("/api/v1/platform/auth/password-reset/confirm", {
            method: "POST", auth: false, body: JSON.stringify({ token, new_password: password }),
          });
          setDone(true);
        } catch (err) {
          setError(err instanceof PlatformApiError ? err.message : "This link is invalid or has expired.");
        } finally {
          setPending(false);
        }
      }}
      className="space-y-4 rounded-lg border border-hairline bg-paper p-6"
    >
      {error && <ErrorState message={error} />}
      <Input
        id="preset-new-password" label="New password" type="password" required minLength={8}
        value={password} onChange={(e) => setPassword(e.target.value)}
      />
      <Button type="submit" disabled={pending} className="w-full">
        {pending ? "Saving…" : "Set new password"}
      </Button>
    </form>
  );
}
