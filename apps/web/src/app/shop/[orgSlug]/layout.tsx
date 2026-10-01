import type { ReactNode } from "react";
import { ShopFooter } from "@/components/shop-footer";

/** Wraps every public storefront page (home, store, listings, cart, blog,
 * FAQs, account, orders…) with the shared footer. Each page still renders
 * its own <ShopHeader/>, exactly as before. */
export default function ShopLayout({ children, params }: { children: ReactNode; params: { orgSlug: string } }) {
  return (
    <>
      {children}
      <ShopFooter orgSlug={params.orgSlug} />
    </>
  );
}
