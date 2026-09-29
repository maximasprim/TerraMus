"use client";

import { useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { ShopHeader } from "@/components/shop-header";
import { Card, Button, Input, ErrorState } from "@/components/ui";
import { apiFetch, setTokens, ApiError } from "@/lib/api";

interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export default function CustomerLoginPage() {
  const { orgSlug } = useParams<{ orgSlug: string }>();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />
      <main className="mx-auto max-w-sm px-6 py-10">
        <Card>
          <h1 className="mb-4 font-display text-2xl text-forest">Log in</h1>
          {error && <div className="mb-3"><ErrorState message={error} /></div>}
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setPending(true);
              setError(null);
              try {
                // Same global endpoint every staff login uses - a customer
                // account is an ordinary login with the Customer role, not
                // a separate auth system (see apps/api's docs/architecture.md
                // Phase 15 note).
                const tokens = await apiFetch<TokenPair>("/api/v1/auth/login", {
                  method: "POST", auth: false, body: JSON.stringify({ email, password }),
                });
                setTokens(tokens.access_token, tokens.refresh_token);
                router.push(`/shop/${orgSlug}/account`);
              } catch (err) {
                setError(err instanceof ApiError ? err.message : "Login failed");
              } finally {
                setPending(false);
              }
            }}
            className="space-y-3"
          >
            <Input id="login-email" label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            <Input id="login-password" label="Password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} />
            <Button type="submit" disabled={pending} className="w-full">
              {pending ? "Logging in…" : "Log in"}
            </Button>
            <p className="text-center text-sm">
              <Link href="/reset-password" className="text-forest hover:underline">
                Forgot your password?
              </Link>
            </p>
          </form>
          <p className="mt-4 text-center text-sm text-muted">
            No account yet?{" "}
            <Link href={`/shop/${orgSlug}/account/register`} className="text-forest hover:underline">
              Create one
            </Link>
          </p>
        </Card>
      </main>
    </div>
  );
}
