"use client";

import { useState } from "react";
import { useLogin } from "@/lib/use-auth";
import { ApiError } from "@/lib/api";
import { Button, ErrorState } from "@/components/ui";

export default function LoginPage() {
  const login = useLogin();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-4">
      <div className="w-full max-w-sm">
        <div className="mb-8 text-center">
          <p className="font-display text-3xl italic text-forest">TerraMus</p>
          <p className="mt-1 text-sm text-muted">Sign in to manage your operation</p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4 rounded-lg border border-hairline bg-white/60 p-6">
          {error && <ErrorState message={error} />}
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-ink">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-hairline bg-white px-3 py-2 text-sm focus:border-brass focus:outline-none"
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium text-ink">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-md border border-hairline bg-white px-3 py-2 text-sm focus:border-brass focus:outline-none"
            />
          </div>
          <Button type="submit" disabled={submitting} className="w-full">
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
          <p className="text-center text-sm">
            <a href="/reset-password" className="text-forest hover:underline">
              Forgot your password?
            </a>
          </p>
          <p className="text-center text-sm text-muted">
            New to Farm Platform?{" "}
            <a href="/register" className="text-forest hover:underline">Set up your farm</a>
          </p>
        </form>
      </div>
    </div>
  );
}
