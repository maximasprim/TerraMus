"use client";

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Card, Button, Input, Textarea, ErrorState, EmptyState } from "@/components/ui";
import { apiFetch, ApiError } from "@/lib/api";
import { clsx } from "clsx";
import type { FarmProfile, Testimonial, BlogPost, FAQ, Banner } from "@/lib/types";

const TABS = ["Profile", "Testimonials", "Blog", "FAQs", "Banners"] as const;
type Tab = (typeof TABS)[number];

export default function CmsPage() {
  const [tab, setTab] = useState<Tab>("Profile");

  return (
    <AdminShell>
      <div className="mb-6">
        <h1 className="font-display text-2xl text-forest">Site content</h1>
        <p className="text-sm text-muted">What shows on your public storefront - farm story, testimonials, blog, FAQs, banners.</p>
      </div>

      <div className="mb-6 flex gap-1 border-b border-hairline">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={clsx(
              "border-b-2 px-3 py-2 text-sm font-medium",
              tab === t ? "border-brass text-forest" : "border-transparent text-muted hover:text-ink",
            )}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "Profile" && <ProfileTab />}
      {tab === "Testimonials" && <TestimonialsTab />}
      {tab === "Blog" && <BlogTab />}
      {tab === "FAQs" && <FaqsTab />}
      {tab === "Banners" && <BannersTab />}
    </AdminShell>
  );
}

function ProfileTab() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Partial<FarmProfile>>({});
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const { data } = useQuery<FarmProfile>({
    queryKey: ["cms-profile"],
    queryFn: () => apiFetch<FarmProfile>("/api/v1/cms/profile"),
  });
  useEffect(() => { if (data) setForm(data); }, [data]);

  const save = useMutation({
    mutationFn: () => apiFetch("/api/v1/cms/profile", { method: "PUT", body: JSON.stringify(form) }),
    onSuccess: (updated) => {
      queryClient.setQueryData(["cms-profile"], updated);
      setSaved(true);
      setError(null);
      setTimeout(() => setSaved(false), 2500);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to save"),
  });

  return (
    <Card className="max-w-xl">
      <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }} className="space-y-4">
        {error && <ErrorState message={error} />}
        {saved && <p className="text-sm text-moss">Saved.</p>}
        <Input label="Farm name" value={form.farm_name ?? ""} onChange={(e) => setForm((f) => ({ ...f, farm_name: e.target.value }))} />
        <Input label="Tagline" value={form.tagline ?? ""} onChange={(e) => setForm((f) => ({ ...f, tagline: e.target.value }))} />
        <Textarea label="Farm story" value={form.farm_story ?? ""} onChange={(e) => setForm((f) => ({ ...f, farm_story: e.target.value }))} />
        <Input label="Logo URL" value={form.logo_url ?? ""} onChange={(e) => setForm((f) => ({ ...f, logo_url: e.target.value }))} />
        <div className="grid grid-cols-2 gap-4">
          <Input label="Address" value={form.address ?? ""} onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))} />
          <Input label="County" value={form.county ?? ""} onChange={(e) => setForm((f) => ({ ...f, county: e.target.value }))} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Input label="Phone" value={form.phone ?? ""} onChange={(e) => setForm((f) => ({ ...f, phone: e.target.value }))} />
          <Input label="Email" type="email" value={form.email ?? ""} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Input label="Website" value={form.website ?? ""} onChange={(e) => setForm((f) => ({ ...f, website: e.target.value }))} />
          <Input
            label="Established year" type="number"
            value={form.established_year ?? ""}
            onChange={(e) => setForm((f) => ({ ...f, established_year: e.target.value ? Number(e.target.value) : null }))}
          />
        </div>
        <Button type="submit" disabled={save.isPending} className="w-full">
          {save.isPending ? "Saving…" : "Save profile"}
        </Button>
      </form>
    </Card>
  );
}

function TestimonialsTab() {
  const queryClient = useQueryClient();
  const [customerName, setCustomerName] = useState("");
  const [quote, setQuote] = useState("");
  const [isPublished, setIsPublished] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { data } = useQuery<Testimonial[]>({
    queryKey: ["cms-testimonials"],
    queryFn: () => apiFetch<Testimonial[]>("/api/v1/cms/testimonials"),
  });

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/cms/testimonials", {
        method: "POST", body: JSON.stringify({ customer_name: customerName, quote, is_published: isPublished }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cms-testimonials"] });
      setCustomerName(""); setQuote(""); setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to add testimonial"),
  });

  const remove = useMutation({
    mutationFn: (id: string) => apiFetch(`/api/v1/cms/testimonials/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cms-testimonials"] }),
  });

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <Card>
        <h2 className="mb-3 font-display text-lg text-forest">Add testimonial</h2>
        <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="space-y-3">
          {error && <ErrorState message={error} />}
          <Input label="Customer name" required value={customerName} onChange={(e) => setCustomerName(e.target.value)} />
          <Textarea label="Quote" required value={quote} onChange={(e) => setQuote(e.target.value)} />
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" checked={isPublished} onChange={(e) => setIsPublished(e.target.checked)} />
            Published (visible on the public site)
          </label>
          <Button type="submit" disabled={create.isPending} className="w-full">
            {create.isPending ? "Adding…" : "Add testimonial"}
          </Button>
        </form>
      </Card>
      <div>
        {data && data.length === 0 && <EmptyState title="No testimonials yet" body="Add your first one." />}
        <div className="space-y-2">
          {data?.map((t) => (
            <Card key={t.id}>
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-ink">{t.customer_name}</p>
                  <p className="text-sm text-muted">"{t.quote}"</p>
                  {!t.is_published && <p className="mt-1 text-xs text-clay">Not published</p>}
                </div>
                <Button variant="ghost" className="text-xs" onClick={() => remove.mutate(t.id)}>Delete</Button>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

function BlogTab() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [excerpt, setExcerpt] = useState("");
  const [body, setBody] = useState("");
  const [isPublished, setIsPublished] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data } = useQuery<BlogPost[]>({
    queryKey: ["cms-blog"],
    queryFn: () => apiFetch<BlogPost[]>("/api/v1/cms/blog"),
  });

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/cms/blog", {
        method: "POST", body: JSON.stringify({ title, excerpt: excerpt || undefined, body, is_published: isPublished }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cms-blog"] });
      setTitle(""); setExcerpt(""); setBody(""); setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to create post"),
  });

  const togglePublish = useMutation({
    mutationFn: ({ id, publish }: { id: string; publish: boolean }) =>
      apiFetch(`/api/v1/cms/blog/${id}`, { method: "PATCH", body: JSON.stringify({ is_published: publish }) }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cms-blog"] }),
  });

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <Card>
        <h2 className="mb-3 font-display text-lg text-forest">New post</h2>
        <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="space-y-3">
          {error && <ErrorState message={error} />}
          <Input label="Title" required value={title} onChange={(e) => setTitle(e.target.value)} />
          <Input label="Excerpt" value={excerpt} onChange={(e) => setExcerpt(e.target.value)} />
          <Textarea label="Body" required value={body} onChange={(e) => setBody(e.target.value)} className="min-h-[160px]" />
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" checked={isPublished} onChange={(e) => setIsPublished(e.target.checked)} />
            Publish immediately
          </label>
          <Button type="submit" disabled={create.isPending} className="w-full">
            {create.isPending ? "Creating…" : "Create post"}
          </Button>
        </form>
      </Card>
      <div>
        {data && data.length === 0 && <EmptyState title="No posts yet" body="Write your first update." />}
        <div className="space-y-2">
          {data?.map((post) => (
            <Card key={post.id}>
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-sm font-medium text-ink">{post.title}</p>
                  <p className="text-xs text-muted">/{post.slug}</p>
                </div>
                <Button
                  variant="ghost"
                  className="text-xs"
                  onClick={() => togglePublish.mutate({ id: post.id, publish: !post.is_published })}
                >
                  {post.is_published ? "Unpublish" : "Publish"}
                </Button>
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

function FaqsTab() {
  const queryClient = useQueryClient();
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [isPublished, setIsPublished] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { data } = useQuery<FAQ[]>({
    queryKey: ["cms-faqs"],
    queryFn: () => apiFetch<FAQ[]>("/api/v1/cms/faqs"),
  });

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/cms/faqs", {
        method: "POST", body: JSON.stringify({ question, answer, is_published: isPublished }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cms-faqs"] });
      setQuestion(""); setAnswer(""); setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to add FAQ"),
  });

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <Card>
        <h2 className="mb-3 font-display text-lg text-forest">Add FAQ</h2>
        <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="space-y-3">
          {error && <ErrorState message={error} />}
          <Input label="Question" required value={question} onChange={(e) => setQuestion(e.target.value)} />
          <Textarea label="Answer" required value={answer} onChange={(e) => setAnswer(e.target.value)} />
          <label className="flex items-center gap-2 text-sm text-ink">
            <input type="checkbox" checked={isPublished} onChange={(e) => setIsPublished(e.target.checked)} />
            Published
          </label>
          <Button type="submit" disabled={create.isPending} className="w-full">
            {create.isPending ? "Adding…" : "Add FAQ"}
          </Button>
        </form>
      </Card>
      <div>
        {data && data.length === 0 && <EmptyState title="No FAQs yet" body="Add your first one." />}
        <div className="space-y-2">
          {data?.map((f) => (
            <Card key={f.id}>
              <p className="text-sm font-medium text-ink">{f.question}</p>
              <p className="text-sm text-muted">{f.answer}</p>
              {!f.is_published && <p className="mt-1 text-xs text-clay">Not published</p>}
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}

function BannersTab() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [linkUrl, setLinkUrl] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data } = useQuery<Banner[]>({
    queryKey: ["cms-banners"],
    queryFn: () => apiFetch<Banner[]>("/api/v1/cms/banners"),
  });

  const create = useMutation({
    mutationFn: () =>
      apiFetch("/api/v1/cms/banners", {
        method: "POST", body: JSON.stringify({ title, image_url: imageUrl, link_url: linkUrl || undefined }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cms-banners"] });
      setTitle(""); setImageUrl(""); setLinkUrl(""); setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Failed to add banner"),
  });

  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <Card>
        <h2 className="mb-3 font-display text-lg text-forest">Add banner</h2>
        <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="space-y-3">
          {error && <ErrorState message={error} />}
          <Input label="Title" required value={title} onChange={(e) => setTitle(e.target.value)} />
          <Input label="Image URL" required value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} />
          <Input label="Link URL (optional)" value={linkUrl} onChange={(e) => setLinkUrl(e.target.value)} />
          <Button type="submit" disabled={create.isPending} className="w-full">
            {create.isPending ? "Adding…" : "Add banner"}
          </Button>
        </form>
      </Card>
      <div>
        {data && data.length === 0 && <EmptyState title="No banners yet" body="Add one to show on your storefront." />}
        <div className="space-y-2">
          {data?.map((b) => (
            <Card key={b.id}>
              <p className="text-sm font-medium text-ink">{b.title}</p>
              <p className="truncate text-xs text-muted">{b.image_url}</p>
              {!b.is_active && <p className="mt-1 text-xs text-clay">Inactive</p>}
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
