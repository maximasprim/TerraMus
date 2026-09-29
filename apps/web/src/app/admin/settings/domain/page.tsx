"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, Input, ErrorState, StatusBadge } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";

interface DnsInstructions {
  a_record: string;
  cname_record: string;
  txt_record_name: string;
  txt_record_value: string;
}

interface DomainStatus {
  domain: string | null;
  verified: boolean;
  dns_instructions: DnsInstructions | null;
  vercel_status?: string | null;
}

export default function DomainSettingsPage() {
  const queryClient = useQueryClient();
  const [domainInput, setDomainInput] = useState("");
  const [error, setError] = useState<string | null>(null);

  const statusQuery = useQuery<DomainStatus>({
    queryKey: ["organization-domain"],
    queryFn: () => apiFetch<DomainStatus>("/api/v1/organization/domain"),
  });

  const setDomain = useMutation({
    mutationFn: (domain: string) =>
      apiFetch<DomainStatus>("/api/v1/organization/domain", { method: "POST", body: JSON.stringify({ domain }) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organization-domain"] });
      setError(null);
      setDomainInput("");
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to set domain"),
  });

  const verifyDomain = useMutation({
    mutationFn: () => apiFetch<DomainStatus>("/api/v1/organization/domain/verify", { method: "POST" }),
    onSuccess: (data) => {
      queryClient.setQueryData(["organization-domain"], data);
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Verification check failed"),
  });

  const removeDomain = useMutation({
    mutationFn: () => apiFetch("/api/v1/organization/domain", { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["organization-domain"] });
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to remove domain"),
  });

  const status = statusQuery.data;

  return (
    <AdminShell>
      <h1 className="mb-1 font-display text-2xl text-forest">Custom domain</h1>
      <p className="mb-6 text-sm text-muted">
        Use your own domain (e.g. terramus.com) for your public storefront, instead of the default address.
      </p>

      {error && <div className="mb-4"><ErrorState message={error} /></div>}
      {statusQuery.error && (
        <ErrorState message={statusQuery.error instanceof ApiError ? statusQuery.error.message : "Failed to load domain status"} />
      )}

      {status && !status.domain && (
        <Card className="max-w-md">
          <p className="mb-3 text-sm font-medium text-ink">Add a domain</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setDomain.mutate(domainInput);
            }}
            className="space-y-3"
          >
            <Input
              id="domain-input" label="Domain" placeholder="terramus.com" required
              value={domainInput} onChange={(e) => setDomainInput(e.target.value)}
            />
            <Button type="submit" disabled={setDomain.isPending} className="w-full">
              {setDomain.isPending ? "Adding…" : "Add domain"}
            </Button>
          </form>
        </Card>
      )}

      {status && status.domain && (
        <Card className="max-w-lg">
          <div className="flex items-center justify-between">
            <p className="font-display text-lg text-forest">{status.domain}</p>
            <StatusBadge status={status.verified ? "active" : "pending"} />
          </div>

          {status.verified ? (
            <p className="mt-3 text-sm text-muted">
              Your storefront is live at{" "}
              <a href={`https://${status.domain}`} target="_blank" rel="noopener noreferrer" className="text-forest hover:underline">
                {status.domain}
              </a>.
            </p>
          ) : (
            <>
              <p className="mt-3 text-sm text-muted">
                Add these records with your domain registrar (e.g. cPanel), then click verify below.
                DNS changes can take anywhere from a few minutes to a few hours to take effect.
              </p>
              {status.dns_instructions && (
                <div className="mt-4 space-y-3 rounded-md bg-white/60 p-4 text-xs">
                  <div>
                    <p className="font-medium text-ink">If using a root domain (e.g. yourfarm.com):</p>
                    <p className="mt-1 font-mono">A record → {status.dns_instructions.a_record}</p>
                  </div>
                  <div>
                    <p className="font-medium text-ink">If using a subdomain (e.g. terramus.com) — recommended:</p>
                    <p className="mt-1 font-mono">CNAME record → {status.dns_instructions.cname_record}</p>
                  </div>
                  <div>
                    <p className="font-medium text-ink">Ownership verification (required, in addition to the above):</p>
                    <p className="mt-1 font-mono">TXT record name: {status.dns_instructions.txt_record_name}</p>
                    <p className="font-mono">TXT record value: {status.dns_instructions.txt_record_value}</p>
                  </div>
                </div>
              )}
              <Button
                className="mt-4 w-full" disabled={verifyDomain.isPending}
                onClick={() => verifyDomain.mutate()}
              >
                {verifyDomain.isPending ? "Checking…" : "Verify domain"}
              </Button>
            </>
          )}

          <Button
            variant="ghost" className="mt-3 w-full text-xs text-clay" disabled={removeDomain.isPending}
            onClick={() => {
              if (window.confirm("Remove this domain? Your storefront will only be reachable at the default address.")) {
                removeDomain.mutate();
              }
            }}
          >
            Remove domain
          </Button>
        </Card>
      )}
    </AdminShell>
  );
}
