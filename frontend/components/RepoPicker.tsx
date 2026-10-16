"use client";

// Pick a repository: with a GitHub token connected, a searchable list of every
// repo the token can access (write access, private, open issues, last push);
// otherwise, or for anything else public, type owner/name or paste a URL.

import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Check, ChevronDown, CircleDot, Github, Loader2, Lock, PenLine, RefreshCw, Search } from "lucide-react";
import { ageLabel, getJSON } from "../lib/api";

export interface MyRepo {
  full_name: string; description: string; private: boolean; fork: boolean; archived: boolean; open_issues: number;
  stars: number; pushed_at: string | null; language: string | null; can_write: boolean; has_issues: boolean;
}

type Sort = "pushed" | "issues" | "name";

export default function RepoPicker({ token, current, loading, onPick }: {
  token: string | null; current: string | null; loading: boolean; onPick: (slug: string) => void;
}) {
  const [repos, setRepos] = useState<MyRepo[] | null>(null);
  const [fetching, setFetching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [sort, setSort] = useState<Sort>("pushed");
  const [writable, setWritable] = useState(true);
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLInputElement>(null);

  const load = async () => {
    if (!token) { setRepos(null); return; }
    setFetching(true);
    setError(null);
    try {
      const data = await getJSON<{ repos: MyRepo[] }>("/repos/mine");
      setRepos(data.repos);
    } catch (e: any) {
      setRepos(null);
      setError(e?.message || "Couldn't list your repositories.");
    } finally {
      setFetching(false);
    }
  };
  useEffect(() => { load(); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Close on outside click.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const filtered = useMemo(() => {
    if (!repos) return [];
    const q = query.trim().toLowerCase();
    let list = repos.filter((r) => !r.archived && (!writable || r.can_write));
    if (q) list = list.filter((r) => `${r.full_name} ${r.description} ${r.language || ""}`.toLowerCase().includes(q));
    if (sort === "issues") list = [...list].sort((a, b) => b.open_issues - a.open_issues);
    if (sort === "name") list = [...list].sort((a, b) => a.full_name.localeCompare(b.full_name));
    return list;
  }, [repos, query, sort, writable]);
  useEffect(() => setActive(0), [query, sort, writable]);

  const typedSlug = /^[\w.-]+\/[\w.-]+$/.test(query.trim()) || query.includes("github.com/") ? query.trim() : null;
  const pick = (slug: string) => { setOpen(false); setQuery(""); onPick(slug); };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(a + 1, Math.max(0, filtered.length - 1))); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Enter") {
      e.preventDefault();
      if (open && filtered[active]) pick(filtered[active].full_name);
      else if (typedSlug) pick(typedSlug);
      else if (query.trim()) pick(query.trim());
    } else if (e.key === "Escape") setOpen(false);
  };

  const hasList = !!token && (repos?.length || fetching || error);
  const writableCount = repos?.filter((r) => r.can_write && !r.archived).length ?? 0;

  return (
    <div ref={box} className="relative">
      <div className="flex flex-col gap-2 sm:flex-row">
        <div className="relative flex-1">
          {hasList ? <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" aria-hidden="true" />
                   : <Github className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" aria-hidden="true" />}
          <input ref={input} className="field h-12 pl-9 pr-10 text-[15px]" value={query}
                 onChange={(e) => { setQuery(e.target.value); if (hasList) setOpen(true); }}
                 onFocus={() => hasList && setOpen(true)} onKeyDown={onKeyDown}
                 placeholder={hasList ? `Search your ${repos?.length ?? ""} repositories, or type owner/name` : "owner/repository or a github.com URL"}
                 aria-label="Repository" role="combobox" aria-expanded={open} aria-controls="repo-list" aria-autocomplete="list"
                 autoComplete="off" spellCheck={false} />
          {hasList && (
            <button type="button" onClick={() => { setOpen((v) => !v); input.current?.focus(); }} aria-label="Show your repositories"
                    className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-stone-500 hover:bg-stone-100 hover:text-ink">
              <ChevronDown className={`h-4 w-4 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden="true" />
            </button>
          )}
        </div>
        <button type="button" className="btn-primary h-12 shrink-0 px-5" disabled={loading || !(typedSlug || query.trim() || (open && filtered[active]))}
                onClick={() => (open && filtered[active] && !typedSlug ? pick(filtered[active].full_name) : query.trim() && pick(typedSlug || query.trim()))}>
          {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <ArrowRight className="h-4 w-4" aria-hidden="true" />} Load
        </button>
      </div>

      {open && hasList && (
        <div className="absolute inset-x-0 top-14 z-30 overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-lift animate-pop">
          <div className="flex flex-wrap items-center gap-1.5 border-b border-stone-100 px-3 py-2 text-[11px]">
            <span className="font-semibold uppercase tracking-wide text-stone-500">Your repositories</span>
            <button type="button" onClick={() => setWritable((v) => !v)} aria-pressed={writable}
                    className={`chip ${writable ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-stone-200 bg-white text-stone-600"}`}>
              <PenLine className="h-3 w-3" aria-hidden="true" /> Can act ({writableCount})
            </button>
            <div role="radiogroup" aria-label="Sort" className="ml-auto flex gap-1">
              {([["pushed", "Recent"], ["issues", "Most issues"], ["name", "A–Z"]] as [Sort, string][]).map(([k, label]) => (
                <button key={k} role="radio" aria-checked={sort === k} type="button" onClick={() => setSort(k)}
                        className={`chip ${sort === k ? "border-ink bg-ink text-paper" : "border-stone-200 bg-white text-stone-600"}`}>{label}</button>
              ))}
            </div>
            <button type="button" onClick={load} aria-label="Refresh the list" className="rounded p-1 text-stone-500 hover:text-ink">
              <RefreshCw className={`h-3.5 w-3.5 ${fetching ? "animate-spin" : ""}`} aria-hidden="true" />
            </button>
          </div>
          <ul id="repo-list" role="listbox" aria-label="Your repositories" className="max-h-80 overflow-y-auto py-1">
            {fetching && !repos && <li className="px-4 py-6 text-center text-xs text-stone-500"><Loader2 className="mx-auto mb-1 h-4 w-4 animate-spin" aria-hidden="true" />Loading your repositories…</li>}
            {error && <li className="px-4 py-3 text-xs text-rose-700">{error}</li>}
            {repos && filtered.length === 0 && (
              <li className="px-4 py-4 text-xs text-stone-500">
                {query && typedSlug ? <>Press <kbd className="kbd">Enter</kbd> to load <strong>{typedSlug}</strong>.</> : writable && repos.length ? "None you can act on match — turn off “Can act” to see read-only ones." : "No repositories match."}
              </li>
            )}
            {filtered.map((r, i) => (
              <li key={r.full_name} role="option" aria-selected={i === active} id={`repo-opt-${i}`}
                  onMouseEnter={() => setActive(i)} onMouseDown={(e) => { e.preventDefault(); pick(r.full_name); }}
                  className={`flex cursor-pointer items-start gap-3 px-4 py-2.5 ${i === active ? "bg-ember-50" : ""}`}>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-sm font-medium text-ink">{r.full_name}</span>
                    {r.private && <Lock className="h-3 w-3 shrink-0 text-stone-500" aria-label="private" />}
                    {r.fork && <span className="chip border-stone-200 bg-stone-50 text-stone-500">fork</span>}
                    {current === r.full_name && <Check className="h-3.5 w-3.5 shrink-0 text-emerald-600" aria-label="loaded" />}
                  </div>
                  {r.description && <p className="truncate text-xs text-stone-500">{r.description}</p>}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-0.5 text-[11px] text-stone-500">
                  <span className={`flex items-center gap-1 ${r.open_issues ? "text-ink" : ""}`}><CircleDot className="h-3 w-3" aria-hidden="true" />{r.open_issues}</span>
                  <span>{r.can_write ? <span className="text-emerald-700">write</span> : "read"} · {ageLabel(r.pushed_at)}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
