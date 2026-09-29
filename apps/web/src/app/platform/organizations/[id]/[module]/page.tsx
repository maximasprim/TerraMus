"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { clsx } from "clsx";
import { PlatformShell } from "@/components/platform-shell";
import { PlatformResourceBrowser } from "@/components/platform-resource-browser";
import { ErrorState } from "@/components/ui";
import { usePlatformMe } from "@/lib/use-platform-auth";
import { PLATFORM_MODULES, getModuleConfig } from "@/lib/platform-modules";

export default function OrgModulePage() {
  const { id, module } = useParams<{ id: string; module: string }>();
  const { data: me } = usePlatformMe();
  const config = getModuleConfig(module);

  return (
    <PlatformShell>
      <div className="mb-1 flex items-center gap-2 text-sm text-muted">
        <Link href="/platform/organizations" className="hover:underline">Organizations</Link>
        <span>/</span>
        <Link href={`/platform/organizations/${id}`} className="hover:underline">Overview</Link>
      </div>
      <h1 className="mb-4 font-display text-2xl text-forest">{config?.label ?? "Unknown module"}</h1>

      <div className="mb-6 flex flex-wrap gap-1 border-b border-hairline">
        <Link
          href={`/platform/organizations/${id}`}
          className="rounded-t-md px-3 py-2 text-sm text-muted hover:bg-white/40"
        >
          Overview
        </Link>
        {PLATFORM_MODULES.map((m) => (
          <Link
            key={m.slug}
            href={`/platform/organizations/${id}/${m.slug}`}
            className={clsx(
              "rounded-t-md px-3 py-2 text-sm",
              m.slug === module ? "bg-white/70 font-medium text-forest" : "text-muted hover:bg-white/40",
            )}
          >
            {m.label}
          </Link>
        ))}
      </div>

      {!config ? (
        <ErrorState message={`Unknown module "${module}".`} />
      ) : (
        <PlatformResourceBrowser orgId={id} config={config} canWrite={me?.role === "superadmin"} />
      )}
    </PlatformShell>
  );
}
