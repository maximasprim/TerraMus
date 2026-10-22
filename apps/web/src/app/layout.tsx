import type { Metadata, Viewport } from "next";
import "./globals.css";
import { QueryProvider } from "@/components/query-provider";
import { SwRegister } from "@/components/sw-register";

// NOTE: next/font/google requires fetching font CSS from fonts.googleapis.com
// at build time, which this sandbox's network egress doesn't allow (same
// constraint documented for the M-Pesa/Stripe providers in apps/api). The
// three font-role CSS variables (--font-fraunces, --font-plex-sans,
// --font-plex-mono) are defined with system-font fallbacks in globals.css
// instead. Swap that one block for real next/font/google calls (Fraunces,
// IBM Plex Sans, IBM Plex Mono - see tailwind.config.ts comments) the moment
// this runs somewhere with network access; no other file needs to change.

export const metadata: Metadata = {
  title: "TerraMus - Farm Management Platform",
  description: "Livestock farm management, ERP & E-commerce platform",
  manifest: "/manifest.json",
  icons: { icon: "/icon-192.png", apple: "/icon-192.png" },
};

export const viewport: Viewport = { themeColor: "#1F3A2E" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <QueryProvider>{children}</QueryProvider>
        <SwRegister />
      </body>
    </html>
  );
}
