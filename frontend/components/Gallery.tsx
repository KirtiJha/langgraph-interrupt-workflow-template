"use client";

// Landing: pick a repository (any public one, or the sample), see its board at a
// glance, choose how much the steward should ask, and launch a mission.

import { useEffect, useState } from "react";
import { ArrowRight, Brain, CircleDot, Eye, Gauge, GitPullRequest, Github, Hand, Loader2, Rocket, Sparkles, Star, Zap } from "lucide-react";
import { Inspection, Mission, getJSON } from "../lib/api";
import RepoPicker from "./RepoPicker";
import { recentRepos, rememberRepo } from "../lib/github";

const ACCENT: Record<string, string> = {
  rose: "from-rose-100 to-rose-50 border-rose-200", amber: "from-amber-100 to-amber-50 border-amber-200",
  sky: "from-sky-100 to-sky-50 border-sky-200", violet: "from-violet-100 to-violet-50 border-violet-200",
  emerald: "from-emerald-100 to-emerald-50 border-emerald-200",
};

export const AUTONOMY_OPTIONS = [
  { id: "observe", label: "Observe", blurb: "Proposes everything, posts nothing.", Icon: Eye },
  { id: "careful", label: "Careful", blurb: "Asks before every action.", Icon: Hand },
  { id: "balanced", label: "Balanced", blurb: "Labels just happen; comments and closes ask.", Icon: Gauge },
  { id: "autopilot", label: "Autopilot", blurb: "Asks only for high-risk or irreversible actions.", Icon: Zap },
];

export default function Gallery({ missions, sampleRepo, offlinePilot, token, autonomy, onAutonomy, userId, onStart, busy }: {
  missions: Mission[]; sampleRepo: string; offlinePilot: boolean; token: string | null;
  autonomy: string; onAutonomy: (a: string) => void; userId: string | null;
  onStart: (repo: string, goal: string, mission: Mission | null) => void; busy: boolean;
}) {
  const [repo, setRepo] = useState<Inspection | null>(null);
  const [inspecting, setInspecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [goal, setGoal] = useState("");
  const [recent, setRecent] = useState<string[]>([]);

  // Missions should work on first paint: open the last repo used, or the sample.
  useEffect(() => {
    const r = recentRepos();
    setRecent(r);
    if (!repo && !inspecting) inspect(r[0] || sampleRepo);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sampleRepo]);

  const inspect = async (slug: string) => {
    setInspecting(true);
    setError(null);
    try {
      const data = await getJSON<Inspection>(`/repos/inspect?repo=${encodeURIComponent(slug)}${userId ? `&user_id=${encodeURIComponent(userId)}` : ""}`);
      setRepo(data);
      if (data.mode === "live") { rememberRepo(data.repo.full_name); setRecent(recentRepos()); }
    } catch (e: any) {
      setRepo(null);
      setError(e?.message || "Couldn't load that repository.");
    } finally {
      setInspecting(false);
    }
  };

  // Re-inspect when the token changes (write access may have changed).
  useEffect(() => { if (repo && repo.mode === "live") inspect(repo.repo.full_name); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const readOnly = !!repo && repo.mode === "live" && !repo.can_write;
  const effectiveAutonomy = readOnly ? "observe" : autonomy;
  const slug = repo?.repo.full_name;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 pb-16 pt-8 sm:pt-12">
      <section className="grid items-start gap-8 lg:grid-cols-[1.2fr_1fr]">
        <div className="min-w-0">
          <span className="chip border-ember-200 bg-ember-50 text-ember-700"><Sparkles className="h-3 w-3" aria-hidden="true" />Human-in-the-loop maintainer agent</span>
          <h1 className="mt-3 font-display text-4xl font-semibold leading-[1.05] tracking-tight text-ink sm:text-5xl">
            Your backlog, triaged.<br /><span className="text-ember-600">Nothing posted without you.</span>
          </h1>
          <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-stone-600">
            Repo Steward reads your issues and pull requests, then proposes labels, replies, closes, release notes and welcomes —
            each with a risk score and a preview. Approve in bulk, edit before it posts, reject with a reason it learns from, rewind if you change your mind.
          </p>

          <div className="mt-6"><RepoPicker token={token} current={repo?.repo.full_name ?? null} loading={inspecting} onPick={inspect} /></div>
          <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-stone-500">
            <button type="button" onClick={() => inspect(sampleRepo)} className="chip border-stone-200 bg-white text-stone-700 hover:border-ember-300 hover:text-ember-700">Try the sample repo</button>
            {recent.map((r) => <button key={r} type="button" onClick={() => inspect(r)} title={r} className="chip max-w-full border-stone-200 bg-white text-stone-700 hover:border-ember-300 hover:text-ember-700"><span className="truncate">{r}</span></button>)}
            <span className="ml-1">{token ? "Pick one of your repositories, or type any public repo." : <>Any public repo works read-only. <strong>Connect GitHub</strong> to list and act on yours.</>}</span>
          </div>
          {error && <p role="alert" className="mt-2 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>}

          <div className="mt-6">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-stone-500">How much should it ask?</div>
            <div role="radiogroup" aria-label="Autonomy" className="mt-2 grid gap-2 sm:grid-cols-4">
              {AUTONOMY_OPTIONS.map(({ id, label, blurb, Icon }) => {
                const active = effectiveAutonomy === id;
                const disabled = readOnly && id !== "observe";
                return (
                  <button key={id} role="radio" aria-checked={active} type="button" onClick={() => !disabled && onAutonomy(id)} disabled={disabled}
                          className={`rounded-xl border p-3 text-left transition-all disabled:cursor-not-allowed disabled:opacity-40 ${active ? "border-ink bg-ink text-paper shadow-lift" : "border-stone-200 bg-white hover:border-stone-300"}`}>
                    <div className="flex items-center gap-1.5 text-sm font-semibold"><Icon className="h-4 w-4" aria-hidden="true" />{label}</div>
                    <div className={`mt-1 text-xs ${active ? "text-paper/70" : "text-stone-500"}`}>{blurb}</div>
                  </button>
                );
              })}
            </div>
            {readOnly && <p className="mt-2 text-xs text-stone-500">No write access to this repo, so the steward will <strong>observe</strong>: every action becomes a proposal you can copy as a checklist. Connect a token to act.</p>}
          </div>
        </div>

        <aside className="card min-w-0 bg-grid p-5">
          {!repo && inspecting ? (
            <div className="animate-pulse space-y-3" aria-label="Loading repository">
              <div className="h-5 w-2/3 rounded bg-stone-200" /><div className="h-3 w-full rounded bg-stone-100" />
              <div className="grid grid-cols-3 gap-2">{[0, 1, 2].map((i) => <div key={i} className="h-16 rounded-xl bg-stone-100" />)}</div>
              <div className="h-3 w-1/2 rounded bg-stone-100" />
            </div>
          ) : !repo ? (
            <>
              <div className="text-[11px] font-semibold uppercase tracking-wide text-stone-500">Repository</div>
              <p className="mt-3 text-sm text-stone-500">Load a repository to see its board: open issues, pull requests, labels — and what the steward remembers about it.</p>
              <ul className="mt-4 space-y-2 text-xs text-stone-600">
                <li>· Public repos load instantly, read-only.</li>
                <li>· With a token, approved actions happen on GitHub.</li>
                <li>· {offlinePilot ? "Offline pilot active: triage, stale sweep, PR review, release notes and welcomes work with no model key." : "A real model is connected: open-ended goals work too."}</li>
              </ul>
            </>
          ) : (
            <>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate text-base font-semibold text-ink">{repo.repo.full_name}</div>
                  {repo.repo.description && <p className="mt-0.5 text-xs text-stone-600">{repo.repo.description}</p>}
                </div>
                <span className={`chip shrink-0 ${repo.mode === "live" ? (repo.can_write ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-violet-200 bg-violet-50 text-violet-700") : "border-stone-200 bg-stone-50 text-stone-600"}`}>
                  {repo.mode === "live" ? (repo.can_write ? "write access" : "read-only") : "sample"}
                </span>
              </div>
              <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
                <div className="rounded-xl bg-white p-3 shadow-sm"><dt className="flex items-center gap-1 text-xs text-stone-500"><CircleDot className="h-3 w-3" aria-hidden="true" />Issues</dt><dd className="tabular text-lg font-semibold text-ink">{repo.issues.length}</dd><dd className="text-[11px] text-stone-500">{repo.issues.filter((i) => !i.labels.length).length} unlabelled</dd></div>
                <div className="rounded-xl bg-white p-3 shadow-sm"><dt className="flex items-center gap-1 text-xs text-stone-500"><GitPullRequest className="h-3 w-3" aria-hidden="true" />PRs</dt><dd className="tabular text-lg font-semibold text-ink">{repo.pulls.length}</dd><dd className="text-[11px] text-stone-500">{repo.pulls.filter((p) => (p.author_association || "").startsWith("FIRST")).length} from first-timers</dd></div>
                <div className="rounded-xl bg-white p-3 shadow-sm"><dt className="flex items-center gap-1 text-xs text-stone-500"><Star className="h-3 w-3" aria-hidden="true" />Stars</dt><dd className="tabular text-lg font-semibold text-ink">{repo.repo.stars.toLocaleString()}</dd><dd className="text-[11px] text-stone-500">{repo.labels.length} labels</dd></div>
              </dl>
              <div className="mt-2 flex flex-wrap gap-1">{repo.labels.slice(0, 8).map((l) => <span key={l.name} className="chip border-stone-200 bg-white text-stone-700" style={{ borderColor: `#${l.color}` }}>{l.name}</span>)}{repo.labels.length > 8 && <span className="text-[11px] text-stone-400">+{repo.labels.length - 8}</span>}</div>
              {repo.rate?.remaining && Number(repo.rate.remaining) < 20 && <p className="mt-2 text-[11px] text-amber-700">GitHub rate limit nearly used ({repo.rate.remaining} left). A token raises it to 5,000/h.</p>}
              <div className="mt-4 border-t border-stone-200/70 pt-3">
                <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-stone-500"><Brain className="h-3.5 w-3.5" aria-hidden="true" />What it remembers about this repo</div>
                {repo.memories.length ? <ul className="mt-2 space-y-1 text-xs text-stone-700">{repo.memories.map((m) => <li key={m}>· {m}</li>)}</ul>
                  : <p className="mt-2 text-xs text-stone-400">Nothing yet — missions leave notes (“uses needs-repro”) that shape the next one.</p>}
              </div>
            </>
          )}
        </aside>
      </section>

      <section className="mt-10">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2 className="text-[11px] font-semibold uppercase tracking-wide text-stone-500">Missions {slug ? `on ${slug}` : ""}</h2>
          {!repo && <span className="text-xs text-stone-400">Load a repository first</span>}
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {missions.map((m) => (
            <button key={m.id} type="button" onClick={() => slug && onStart(slug, m.goal, m)} disabled={busy || !slug}
                    className={`group flex flex-col rounded-2xl border bg-gradient-to-br p-4 text-left shadow-card transition-all hover:-translate-y-0.5 hover:shadow-lift disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 ${ACCENT[m.accent] || ACCENT.sky}`}>
              <div className="flex items-start justify-between">
                <span className="text-3xl" aria-hidden="true">{m.emoji}</span>
                <span className="chip border-white/60 bg-white/70 text-stone-600"><Hand className="h-3 w-3" aria-hidden="true" />~{m.approvals} approvals</span>
              </div>
              <h3 className="mt-3 text-base font-semibold leading-snug text-ink">{m.title}</h3>
              <p className="mt-1 text-[13px] text-stone-600">{m.blurb}</p>
              <div className="mt-3 flex flex-wrap gap-1">{m.tags.map((t) => <span key={t} className="chip border-white/60 bg-white/60 text-stone-600">{t}</span>)}</div>
              <span className="mt-4 flex items-center gap-1 text-sm font-semibold text-ink opacity-70 transition-opacity group-hover:opacity-100">Launch <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" aria-hidden="true" /></span>
            </button>
          ))}
          <form className="flex flex-col rounded-2xl border border-dashed border-stone-300 bg-white/60 p-4" onSubmit={(e) => { e.preventDefault(); if (slug && goal.trim()) onStart(slug, goal.trim(), null); }}>
            <span className="text-3xl" aria-hidden="true">✍️</span>
            <h3 className="mt-3 text-base font-semibold leading-snug text-ink">Your own goal</h3>
            <textarea className="field mt-2 min-h-20 flex-1 text-[13px]" value={goal} onChange={(e) => setGoal(e.target.value)}
                      placeholder={offlinePilot ? "Needs a real model — add one under Model in the header." : "e.g. Find issues that are really feature requests and relabel them"} aria-label="Your goal" />
            <button type="submit" className="btn-accent mt-3 self-start" disabled={busy || !slug || !goal.trim()}><Rocket className="h-4 w-4" aria-hidden="true" /> Launch</button>
          </form>
        </div>
      </section>
    </div>
  );
}
