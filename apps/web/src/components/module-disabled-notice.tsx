/**
 * Shown on a module's list page when a platform admin has switched that module
 * off for the organization. Existing records stay visible; only creating new
 * ones is blocked (the API enforces this) - the notice says so up front rather
 * than letting people discover it from a 403.
 */
export function ModuleDisabledNotice({ module }: { module: "Livestock" | "Crops" }) {
  return (
    <div className="mb-6 rounded-lg border border-brass/40 bg-brass/10 px-4 py-3 text-sm text-ink">
      <p className="font-medium">{module} is switched off for your organization.</p>
      <p className="mt-0.5 text-muted">
        You can still view existing records, but new ones can&apos;t be added. Contact your platform
        administrator if you need {module.toLowerCase()} enabled.
      </p>
    </div>
  );
}
