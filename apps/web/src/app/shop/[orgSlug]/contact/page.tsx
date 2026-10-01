"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Mail, MapPin, MessageCircle, Phone } from "lucide-react";
import { ShopHeader } from "@/components/shop-header";
import { Button, ErrorState, Input, Textarea } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { shopPath, usePageTitle, useShopProfile, whatsappLink } from "@/lib/shop-utils";

export default function ContactPage() {
  // useSearchParams (for ?product=...) needs a Suspense boundary.
  return (
    <Suspense fallback={<div className="min-h-screen bg-paper" />}>
      <ContactInner />
    </Suspense>
  );
}

function ContactInner() {
  const { orgSlug } = useParams<{ orgSlug: string }>();
  const product = useSearchParams().get("product") ?? "";
  const { data: profile } = useShopProfile(orgSlug);
  usePageTitle(profile ? "Contact us" : undefined, profile?.farm_name);

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [message, setMessage] = useState(product ? `Hello, I'd like to ask about "${product.replace(/-/g, " ")}".\n\n` : "");
  const [honeypot, setHoneypot] = useState(""); // hidden field - real visitors never fill it
  const [error, setError] = useState<string | null>(null);

  const send = useMutation({
    mutationFn: () =>
      apiFetch<{ received: boolean }>(`/api/v1/public/${orgSlug}/contact`, {
        method: "POST",
        auth: false,
        body: JSON.stringify({
          name,
          email: email.trim() || undefined,
          phone: phone.trim() || undefined,
          message,
          listing_slug: product || undefined,
          website: honeypot || undefined,
        }),
      }),
    onSuccess: () => setError(null),
    onError: (err) => {
      if (err instanceof ApiError && err.status === 429) setError("You've sent several messages recently - please try again in a few minutes, or call us.");
      else if (err instanceof ApiError && err.status === 422) setError("Please check your details: add a name, a message of a few words, and an email or phone number so we can reply.");
      else setError(err instanceof ApiError ? err.message : "Couldn't send your message - please try again or contact us directly.");
    },
  });

  const composed = `Hello ${profile?.farm_name ?? ""},\n\n${message}\n\n- ${name}${phone ? ` (${phone})` : ""}`;
  const wa = whatsappLink(profile?.phone, composed);
  const mail = profile?.email ? `mailto:${profile.email}?subject=${encodeURIComponent(`Enquiry from ${name || "a customer"}`)}&body=${encodeURIComponent(composed)}` : null;
  const canSend = name.trim() !== "" && message.trim().length >= 5 && (email.trim() !== "" || phone.trim() !== "");
  const mapQuery = [profile?.address, profile?.county, "Kenya"].filter(Boolean).join(", ");

  const cards = [
    profile?.phone && { Icon: Phone, title: "Call us", value: profile.phone, href: `tel:${profile.phone}` },
    profile?.email && { Icon: Mail, title: "Email us", value: profile.email, href: `mailto:${profile.email}` },
    (profile?.address || profile?.county) && {
      Icon: MapPin,
      title: "Visit the farm",
      value: [profile?.address, profile?.county].filter(Boolean).join(", "),
      href: `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(mapQuery)}`,
    },
  ].filter(Boolean) as { Icon: typeof Phone; title: string; value: string; href: string }[];

  return (
    <div className="min-h-screen bg-paper">
      <ShopHeader orgSlug={orgSlug} />

      <section className="bg-gradient-to-br from-forest to-ink text-paper">
        <div className="mx-auto max-w-4xl px-4 py-14 text-center sm:px-6">
          <h1 className="font-display text-4xl">Contact us</h1>
          <p className="mt-2 text-paper/80">Questions, bulk orders or a farm visit? We&apos;d love to hear from you.</p>
        </div>
      </section>

      <main className="mx-auto grid max-w-5xl gap-8 px-4 py-12 sm:px-6 md:grid-cols-2">
        <div className="space-y-4">
          {cards.length === 0 && (
            <p className="rounded-lg border border-hairline bg-white p-5 text-sm text-muted">
              Use the form to send us a message, or browse the <Link className="text-forest underline" href={shopPath(orgSlug, "/store")}>store</Link> and order online.
            </p>
          )}
          {cards.map(({ Icon, title, value, href }) => (
            <a key={title} href={href} target={href.startsWith("http") ? "_blank" : undefined} rel="noreferrer" className="flex items-start gap-4 rounded-lg border border-hairline bg-white p-5 transition-shadow hover:shadow-md">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-forest/10 text-forest"><Icon className="h-5 w-5" aria-hidden /></span>
              <span>
                <span className="block font-semibold text-ink">{title}</span>
                <span className="block break-words text-sm text-muted">{value}</span>
              </span>
            </a>
          ))}
          <p className="text-sm text-muted">
            Looking for quick answers? Check our <Link className="text-forest underline" href={shopPath(orgSlug, "/faqs")}>FAQs</Link>.
          </p>
        </div>

        <div className="rounded-lg border border-hairline bg-white p-6">
          {send.isSuccess ? (
            <div className="py-6 text-center">
              <CheckCircle2 className="mx-auto h-10 w-10 text-forest" aria-hidden />
              <h2 className="mt-3 font-display text-xl text-forest">Message sent</h2>
              <p className="mt-1 text-sm text-muted">Thank you{name ? `, ${name}` : ""}! {profile?.farm_name ?? "The farm"} will get back to you soon.</p>
              <Link href={shopPath(orgSlug, "/store")} className="mt-5 inline-block rounded-md bg-brass px-5 py-2.5 text-sm font-semibold text-ink hover:bg-brass/90">
                Continue shopping
              </Link>
            </div>
          ) : (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                setError(null);
                send.mutate();
              }}
              className="space-y-3"
            >
              <h2 className="font-display text-xl text-forest">Send a message</h2>
              {error && <ErrorState message={error} />}
              <Input id="contact-name" label="Your name" required value={name} onChange={(e) => setName(e.target.value)} />
              <div className="grid gap-3 sm:grid-cols-2">
                <Input id="contact-email" label="Email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
                <Input id="contact-phone" label="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
              </div>
              <p className="-mt-1 text-xs text-muted">Add an email or phone number so we can reply.</p>
              <Textarea id="contact-message" label="Message" rows={5} required value={message} onChange={(e) => setMessage(e.target.value)} />

              {/* honeypot: hidden from people and assistive tech, tempting to bots */}
              <div aria-hidden className="absolute -left-[9999px] h-0 w-0 overflow-hidden">
                <label>Website<input tabIndex={-1} autoComplete="off" value={honeypot} onChange={(e) => setHoneypot(e.target.value)} /></label>
              </div>

              <Button type="submit" disabled={!canSend || send.isPending} className="w-full">
                {send.isPending ? "Sending…" : "Send message"}
              </Button>

              {(wa || mail) && (
                <p className="pt-1 text-center text-xs text-muted">
                  Prefer to message directly?{" "}
                  {wa && <a className="text-forest underline" href={canSend ? wa : undefined} target="_blank" rel="noreferrer"><MessageCircle className="mr-0.5 inline h-3 w-3" aria-hidden />WhatsApp</a>}
                  {wa && mail && " · "}
                  {mail && <a className="text-forest underline" href={canSend ? mail : undefined}>Email</a>}
                </p>
              )}
            </form>
          )}
        </div>
      </main>
    </div>
  );
}
