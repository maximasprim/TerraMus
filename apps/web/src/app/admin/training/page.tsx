"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AdminShell } from "@/components/admin-shell";
import { Button, Card, EmptyState, ErrorState, Input, Modal, Select, StatusBadge } from "@/components/ui";
import { apiDownload, apiFetch, ApiError } from "@/lib/api";

interface Course { id: string; title: string; duration_days: number; fee: number; capacity: number | null; trainer: string | null }
interface Session {
  id: string; course_id: string; course_title: string; start_date: string; end_date: string; venue: string | null;
  capacity: number | null; seats_left: number | null; enrolled: number; fee: number; status: string; fees_charged: number;
}
interface Roster {
  roster: { id: string; participant_name: string; phone: string | null; status: string; paid: number; outstanding: number; days_present: number; certificate_number: string | null }[];
  collected: number; outstanding: number; fees_charged: number; total_days: number;
}
const today = () => new Date().toISOString().slice(0, 10);
const errMsg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f);
const kes = (n: number) => new Intl.NumberFormat("en-KE", { maximumFractionDigits: 0 }).format(n);

export default function TrainingPage() {
  const queryClient = useQueryClient();
  const [courseOpen, setCourseOpen] = useState(false);
  const [sessOpen, setSessOpen] = useState(false);
  const [enrolFor, setEnrolFor] = useState<Session | null>(null);
  const [rosterFor, setRosterFor] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [c, setC] = useState({ title: "", duration_days: "1", fee: "", capacity: "", trainer: "" });
  const [s, setS] = useState({ course_id: "", start_date: today(), venue: "" });
  const [p, setP] = useState({ participant_name: "", phone: "" });

  const courses = useQuery<Course[]>({ queryKey: ["training", "courses"], queryFn: () => apiFetch<Course[]>("/api/v1/training/courses") });
  const sessions = useQuery<Session[]>({ queryKey: ["training", "sessions"], queryFn: () => apiFetch<Session[]>("/api/v1/training/sessions") });
  const roster = useQuery<Roster>({ queryKey: ["training", "roster", rosterFor?.id], enabled: !!rosterFor, queryFn: () => apiFetch<Roster>(`/api/v1/training/sessions/${rosterFor?.id}`) });
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["training"] });
  const fail = (f: string) => (e: unknown) => setError(errMsg(e, f));

  const mkCourse = useMutation({
    mutationFn: () => apiFetch("/api/v1/training/courses", { method: "POST", body: JSON.stringify({
      title: c.title, duration_days: Number(c.duration_days) || 1, fee: c.fee || "0", capacity: c.capacity ? Number(c.capacity) : undefined, trainer: c.trainer || undefined }) }),
    onSuccess: () => { refresh(); setCourseOpen(false); setError(null); }, onError: fail("Could not create course"),
  });
  const mkSession = useMutation({
    mutationFn: () => apiFetch("/api/v1/training/sessions", { method: "POST", body: JSON.stringify({ course_id: s.course_id, start_date: s.start_date, venue: s.venue || undefined }) }),
    onSuccess: () => { refresh(); setSessOpen(false); setError(null); }, onError: fail("Could not schedule session"),
  });
  const enrol = useMutation({
    mutationFn: () => apiFetch(`/api/v1/training/sessions/${enrolFor?.id}/enrolments`, { method: "POST", body: JSON.stringify({ participant_name: p.participant_name, phone: p.phone || undefined }) }),
    onSuccess: () => { refresh(); setEnrolFor(null); setP({ participant_name: "", phone: "" }); setError(null); }, onError: fail("Could not enrol participant"),
  });
  const present = useMutation({
    mutationFn: (id: string) => apiFetch(`/api/v1/training/enrolments/${id}/attendance`, { method: "POST", body: JSON.stringify({ day: today(), present: true }) }),
    onSuccess: refresh, onError: fail("Could not mark attendance"),
  });
  const certify = useMutation({
    mutationFn: async (id: string) => {
      await apiFetch(`/api/v1/training/enrolments/${id}/certificate`, { method: "POST", body: JSON.stringify({}) });
      await apiDownload(`/api/v1/training/enrolments/${id}/certificate.pdf`, "certificate.pdf");
    },
    onSuccess: refresh, onError: fail("Could not issue certificate"),
  });

  return (
    <AdminShell>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl text-forest">Training</h1>
          <p className="text-sm text-muted">Courses, sessions, enrolments (billed to the participant), attendance and certificates.</p>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" onClick={() => { setError(null); setCourseOpen(true); }}>+ Course</Button>
          <Button onClick={() => { setError(null); setS({ ...s, course_id: courses.data?.[0]?.id ?? "" }); setSessOpen(true); }} disabled={!courses.data?.length}>+ Session</Button>
        </div>
      </div>
      {error && !courseOpen && !sessOpen && !enrolFor && <ErrorState message={error} />}
      {sessions.isLoading && <p className="text-sm text-muted">Loading…</p>}
      {sessions.data && sessions.data.length === 0 && <EmptyState title="No training sessions yet" body="Create a course, then schedule a session." />}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {sessions.data?.map((x) => (
          <Card key={x.id} className="space-y-2">
            <div className="flex items-center justify-between"><span className="text-xs text-muted">{x.start_date}{x.end_date !== x.start_date ? ` → ${x.end_date}` : ""}</span><StatusBadge status={x.status} /></div>
            <p className="font-display text-lg text-forest">{x.course_title}</p>
            <p className="text-sm text-muted">{x.venue ?? "No venue"} · KES {kes(x.fee)}</p>
            <p className="text-sm">{x.enrolled} enrolled{x.capacity ? ` of ${x.capacity}` : ""} · KES {kes(x.fees_charged)} billed</p>
            <div className="flex gap-2">
              <Button variant="ghost" disabled={x.seats_left === 0 || ["completed", "cancelled"].includes(x.status)} onClick={() => { setError(null); setEnrolFor(x); }}>Enrol</Button>
              <Button variant="ghost" onClick={() => setRosterFor(x)}>Roster</Button>
            </div>
          </Card>))}
      </div>
      <Modal open={courseOpen} onClose={() => setCourseOpen(false)} title="New course">
        <div className="space-y-3">{error && <ErrorState message={error} />}
          <Input label="Title" value={c.title} onChange={(e) => setC({ ...c, title: e.target.value })} />
          <Input label="Duration (days)" type="number" min="1" value={c.duration_days} onChange={(e) => setC({ ...c, duration_days: e.target.value })} />
          <Input label="Fee per participant (KES)" type="number" min="0" value={c.fee} onChange={(e) => setC({ ...c, fee: e.target.value })} />
          <Input label="Capacity (optional)" type="number" min="1" value={c.capacity} onChange={(e) => setC({ ...c, capacity: e.target.value })} />
          <Input label="Trainer" value={c.trainer} onChange={(e) => setC({ ...c, trainer: e.target.value })} />
          <Button disabled={c.title.length < 2 || mkCourse.isPending} onClick={() => mkCourse.mutate()}>Create course</Button></div>
      </Modal>
      <Modal open={sessOpen} onClose={() => setSessOpen(false)} title="Schedule a session">
        <div className="space-y-3">{error && <ErrorState message={error} />}
          <Select label="Course" value={s.course_id} onChange={(e) => setS({ ...s, course_id: e.target.value })}>
            {courses.data?.map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}</Select>
          <Input label="Start date" type="date" value={s.start_date} onChange={(e) => setS({ ...s, start_date: e.target.value })} />
          <Input label="Venue" value={s.venue} onChange={(e) => setS({ ...s, venue: e.target.value })} />
          <Button disabled={!s.course_id || mkSession.isPending} onClick={() => mkSession.mutate()}>Schedule</Button></div>
      </Modal>
      <Modal open={!!enrolFor} onClose={() => setEnrolFor(null)} title={`Enrol in ${enrolFor?.course_title ?? ""}`}>
        <div className="space-y-3">{error && <ErrorState message={error} />}
          <Input label="Participant name" value={p.participant_name} onChange={(e) => setP({ ...p, participant_name: e.target.value })} />
          <Input label="Phone" value={p.phone} onChange={(e) => setP({ ...p, phone: e.target.value })} />
          <p className="text-xs text-muted">KES {kes(enrolFor?.fee ?? 0)} will be billed to this participant. Record their payment under Receivables.</p>
          <Button disabled={p.participant_name.length < 2 || enrol.isPending} onClick={() => enrol.mutate()}>Enrol</Button></div>
      </Modal>
      <Modal open={!!rosterFor} onClose={() => setRosterFor(null)} title={`Roster: ${rosterFor?.course_title ?? ""}`} size="lg">
        {roster.isLoading && <p className="text-sm text-muted">Loading…</p>}
        {roster.data && (
          <div className="space-y-3 text-sm">
            <p>Billed KES {kes(roster.data.fees_charged)} · collected KES {kes(roster.data.collected)} · outstanding <b>KES {kes(roster.data.outstanding)}</b></p>
            {error && <ErrorState message={error} />}
            <table className="w-full"><tbody>{roster.data.roster.map((r) => (
              <tr key={r.id} className="border-b border-hairline/60">
                <td className="py-1.5 font-medium">{r.participant_name}<div className="text-xs text-muted">{r.phone}</div></td>
                <td><StatusBadge status={r.status} /></td>
                <td className="text-xs">{r.days_present}/{roster.data.total_days} days</td>
                <td className="text-right text-xs">{r.outstanding > 0 ? <span className="text-clay">owes {kes(r.outstanding)}</span> : "paid"}</td>
                <td className="space-x-1 text-right">
                  {r.status !== "cancelled" && <Button variant="ghost" onClick={() => present.mutate(r.id)}>Present today</Button>}
                  {r.status !== "cancelled" && <Button variant="ghost" onClick={() => certify.mutate(r.id)}>{r.certificate_number ? "Certificate" : "Issue certificate"}</Button>}
                </td>
              </tr>))}</tbody></table>
          </div>
        )}
      </Modal>
    </AdminShell>
  );
}
