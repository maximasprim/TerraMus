"use client";

import { useState } from "react";
import Link from "next/link";
import { useRegisterOrganization } from "@/lib/use-auth";
import { ApiError } from "@/lib/api";
import { Button, Input, ErrorState } from "@/components/ui";

export default function RegisterPage() {
  const register = useRegisterOrganization();
  const [organizationName, setOrganizationName] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="font-display text-3xl italic text-forest">TerraMus</p>
          <p className="mt-1 text-sm text-muted">Set up your farm's account</p>
        </div>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setError(null);
            setSubmitting(true);
            try {
              await register({
                organization_name: organizationName, full_name: fullName,
                email, phone: phone || undefined, password,
              });
            } catch (err) {
              setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
            } finally {
              setSubmitting(false);
            }
          }}
          className="space-y-4 rounded-lg border border-hairline bg-white/60 p-6"
        >
          {error && <ErrorState message={error} />}
          <Input
            id="reg-org-name" label="Farm / organization name" required
            value={organizationName} onChange={(e) => setOrganizationName(e.target.value)}
            placeholder="e.g. Green Valley Dairy Farm"
          />
          <Input
            id="reg-full-name" label="Your full name" required
            value={fullName} onChange={(e) => setFullName(e.target.value)}
          />
          <Input
            id="reg-email" label="Email" type="email" required
            value={email} onChange={(e) => setEmail(e.target.value)}
          />
          <Input
            id="reg-phone" label="Phone (optional)"
            value={phone} onChange={(e) => setPhone(e.target.value)}
          />
          <Input
            id="reg-password" label="Password" type="password" required minLength={8}
            value={password} onChange={(e) => setPassword(e.target.value)}
          />
          <p className="text-xs text-muted">
            You'll be the Farm Owner - able to invite staff and configure everything afterward.
          </p>
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Creating your account…" : "Create farm account"}
          </Button>
          <p className="text-center text-sm">
            Already have an account?{" "}
            <Link href="/login" className="text-forest hover:underline">Sign in</Link>
          </p>
        </form>
      </div>
    </div>
  );
}
