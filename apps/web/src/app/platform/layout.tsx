import { PlatformShellLayout } from "@/components/platform-shell";

/**
 * One persistent shell for the signed-in /platform console (the login and reset-password pages are
 * left bare by PlatformShellLayout). Pages still wrap themselves in <PlatformShell>; inside this
 * layout that is a no-op.
 */
export default function PlatformLayout({ children }: { children: React.ReactNode }) {
  return <PlatformShellLayout>{children}</PlatformShellLayout>;
}
