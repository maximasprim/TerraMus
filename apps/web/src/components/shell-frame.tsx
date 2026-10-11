"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { clsx } from "clsx";
import { Menu } from "lucide-react";

/**
 * The window layout shared by the tenant and platform consoles.
 *
 *  - The shell fills the window exactly (fixed to it) and never scrolls itself. The sidebar
 *    stays put; its header and sign-out stay pinned and only the menu in the
 *    middle scrolls if it is taller than the window.
 *  - The right-hand panel is its own scroll container, so a long page (the
 *    reports page, a big table) scrolls inside the panel and the sidebar does
 *    not move with it.
 *  - Below the `lg` breakpoint the sidebar becomes a slide-in drawer opened from
 *    a slim top bar, so phones get the full width for content.
 *
 * Because the content scrolls inside <main> rather than the window, navigating
 * must reset <main>'s scroll position itself (the browser only resets the window).
 */
export function ShellFrame({
  sidebarClassName,
  brand,
  nav,
  footer,
  mobileTitle,
  mainClassName = "p-8",
  children,
}: {
  /** Colour classes for the sidebar (e.g. "bg-forest"). */
  sidebarClassName: string;
  /** Pinned block at the top of the sidebar. */
  brand: ReactNode;
  /** The menu links; rendered inside the scrolling <nav>. */
  nav: ReactNode;
  /** Pinned block at the bottom of the sidebar (sign out, notices). */
  footer: ReactNode;
  /** Shown in the top bar on small screens. */
  mobileTitle: ReactNode;
  mainClassName?: string;
  children: ReactNode;
}) {
  const pathname = usePathname() ?? "";
  const [open, setOpen] = useState(false);
  const mainRef = useRef<HTMLElement>(null);

  // A new page starts at the top, and the mobile drawer closes after choosing a link.
  useEffect(() => {
    setOpen(false);
    if (mainRef.current) mainRef.current.scrollTop = 0;
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    // `fixed inset-0` pins the shell to the visible window, so the page itself can never scroll
    // (no second scrollbar, no blank band under the shell). It also makes the shell the containing
    // block for absolutely-positioned descendants such as the screen-reader-only chart tables;
    // without a positioned ancestor those escape the clipping and stretch the document.
    // Deliberately not h-screen/h-dvh: viewport units are unreliable in embedded browser panels.
    <div className="shell-root fixed inset-0 flex overflow-hidden bg-paper">
      {open && (
        <div
          data-testid="shell-backdrop"
          className="no-print fixed inset-0 z-30 bg-ink/50 lg:hidden"
          onClick={() => setOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside
        id="app-sidebar"
        className={clsx(
          "flex h-full w-60 shrink-0 flex-col border-r border-hairline text-paper",
          "fixed inset-y-0 left-0 z-40 transition-[transform,visibility] duration-200 lg:static lg:translate-x-0",
          // Off-canvas on small screens: also hidden from keyboard/screen readers until opened.
          open ? "translate-x-0" : "invisible -translate-x-full lg:visible",
          sidebarClassName,
        )}
      >
        <div className="shrink-0">{brand}</div>
        <nav className="flex-1 space-y-1 overflow-y-auto px-3 py-4">{nav}</nav>
        <div className="shrink-0">{footer}</div>
      </aside>

      <div className="shell-body flex min-w-0 flex-1 flex-col">
        <header className="no-print flex shrink-0 items-center gap-3 border-b border-hairline bg-white/60 px-4 py-3 lg:hidden">
          <button
            type="button"
            aria-label="Open navigation"
            aria-expanded={open}
            aria-controls="app-sidebar"
            onClick={() => setOpen(true)}
            className="rounded-md p-1.5 text-ink hover:bg-hairline/50 focus:outline-none focus-visible:ring-2 focus-visible:ring-brass"
          >
            <Menu size={20} />
          </button>
          <span className="min-w-0 truncate font-display text-lg italic text-forest">{mobileTitle}</span>
        </header>

        <main ref={mainRef} className={clsx("relative min-w-0 flex-1 overflow-y-auto", mainClassName)}>
          {children}
        </main>
      </div>
    </div>
  );
}
