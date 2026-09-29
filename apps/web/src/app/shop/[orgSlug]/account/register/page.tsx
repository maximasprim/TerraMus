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

export default function CustomerRegisterPage() {
  const { orgSlug } = useParams<{ orgSlug: string }>();
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />
      <main className="mx-auto max-w-sm px-6 py-10">
        <Card>
          <h1 className="mb-1 font-display text-2xl text-forest">Create an account</h1>
          <p className="mb-4 text-sm text-muted">
            Track your orders and reservations. Already ordered as a guest? Use the same email
            here to link your past order automatically.
          </p>
          {error && <div className="mb-3"><ErrorState message={error} /></div>}
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setPending(true);
              setError(null);
              try {
                const tokens = await apiFetch<TokenPair>(`/api/v1/public/${orgSlug}/account/register`, {
                  method: "POST",
                  auth: false,
                  body: JSON.stringify({
                    full_name: fullName, email, phone: phone || undefined, password,
                  }),
                });
                setTokens(tokens.access_token, tokens.refresh_token);
                router.push(`/shop/${orgSlug}/account`);
              } catch (err) {
                setError(err instanceof ApiError ? err.message : "Registration failed");
              } finally {
                setPending(false);
              }
            }}
            className="space-y-3"
          >
            <Input id="reg-name" label="Full name" required value={fullName} onChange={(e) => setFullName(e.target.value)} />
            <Input id="reg-email" label="Email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} />
            <Input id="reg-phone" label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
            <Input
              id="reg-password" label="Password" type="password" required minLength={8}
              value={password} onChange={(e) => setPassword(e.target.value)}
            />
            <Button type="submit" disabled={pending} className="w-full">
              {pending ? "Creating account…" : "Create account"}
            </Button>
          </form>
          <p className="mt-4 text-center text-sm text-muted">
            Already have an account?{" "}
            <Link href={`/shop/${orgSlug}/account/login`} className="text-forest hover:underline">
              Log in
            </Link>
          </p>
        </Card>
      </main>
    </div>
  );
}
