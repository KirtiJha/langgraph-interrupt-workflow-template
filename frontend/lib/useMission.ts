"use client";

// The mission state machine: SSE events → feed, live board, pending decisions,
// status — and the actions (start, decide, fork, pause, follow-up, restore).

import { useCallback, useEffect, useReducer, useRef } from "react";
import { Approval, Board, Decision, DecisionPoint, MissionState, Question, Report, describeCall, getJSON, postJSON, stream } from "./api";
import { describeError } from "./modelSettings";

export type CallStatus = "running" | "pending" | "ok" | "rejected" | "edited" | "responded" | "error";

export interface ToolCall { id: string; name: string; args: Record<string, any>; status: CallStatus; result?: string }

export type Entry =
  | { kind: "goal"; id: string; text: string }
  | { kind: "narration"; id: string; text: string; streaming: boolean }
  | { kind: "tools"; id: string; calls: ToolCall[] }
  | { kind: "change"; id: string; ops: any[] }
  | { kind: "decision"; id: string; text: string; tone: "approve" | "reject" | "edit" | "respond" | "answer" }
  | { kind: "report"; id: string; report: Report }
  | { kind: "system"; id: string; text: string; tone?: "info" | "warn" | "error" | "memory" | "branch" };

export interface MissionUI {
  threadId: string | null;
  title: string;
  missionId: string | null;
  goal: string;
  repo: string;
  mode: "live" | "fixture";
  canWrite: boolean;
  feed: Entry[];
  board: Board | null;
  pending: { approvals: Approval[]; question: Question | null };
  status: MissionState["status"] | "starting" | "streaming";
  streaming: boolean;
  report: Report | null;
  autonomy: string;
  decisionsMade: number;
  branches: number;
  history: DecisionPoint[];
  error: string | null;
}

const initial: MissionUI = {
  threadId: null, title: "", missionId: null, goal: "", repo: "", mode: "fixture", canWrite: true, feed: [], board: null,
  pending: { approvals: [], question: null }, status: "idle", streaming: false, report: null, autonomy: "careful",
  decisionsMade: 0, branches: 1, history: [], error: null,
};

let seq = 0;
const uid = () => `e${++seq}`;

type Action =
  | { type: "reset"; goal: string; title: string; missionId: string | null; repo: string; autonomy: string }
  | { type: "event"; event: any }
  | { type: "stream"; on: boolean }
  | { type: "decided"; entries: Entry[]; count: number }
  | { type: "history"; points: DecisionPoint[] }
  | { type: "branch" }
  | { type: "error"; message: string | null }
  | { type: "restore"; state: MissionState; feed: Entry[]; threadId: string; title: string };

function lastNarration(feed: Entry[]): Entry | undefined {
  const e = feed[feed.length - 1];
  return e && e.kind === "narration" && e.streaming ? e : undefined;
}

function applyResult(feed: Entry[], ev: any, pendingName?: boolean): boolean {
  for (let i = feed.length - 1; i >= 0; i--) {
    const e = feed[i];
    if (e.kind !== "tools") continue;
    const idx = e.calls.findIndex((c) => c.id === ev.id);
    if (idx < 0) continue;
    if (["ok", "edited", "error"].includes(e.calls[idx].status)) return false; // re-delivered on resume
    const calls = e.calls.slice();
    const status: CallStatus = ev.status === "rejected" ? "rejected" : ev.status === "edited" ? "edited"
      : calls[idx].status === "responded" ? "responded" : /^GitHub refused|^Couldn't/.test(ev.content || "") ? "error" : "ok";
    calls[idx] = { ...calls[idx], status, result: ev.content };
    feed[i] = { ...e, calls };
    return true;
  }
  return false;
}

function reduce(s: MissionUI, a: Action): MissionUI {
  switch (a.type) {
    case "reset":
      return { ...initial, goal: a.goal, title: a.title, missionId: a.missionId, repo: a.repo, autonomy: a.autonomy,
               status: "starting", streaming: true, feed: a.goal ? [{ kind: "goal", id: uid(), text: a.goal }] : [] };
    case "stream":
      return { ...s, streaming: a.on, status: a.on && s.status === "idle" ? "streaming" : s.status };
    case "decided":
      return { ...s, feed: [...s.feed, ...a.entries], decisionsMade: s.decisionsMade + a.count,
               pending: { approvals: [], question: null }, streaming: true, status: "streaming" };
    case "history":
      return { ...s, history: a.points };
    case "branch":
      return { ...s, branches: s.branches + 1, streaming: true, status: "streaming", pending: { approvals: [], question: null },
               feed: [...s.feed, { kind: "system", id: uid(), tone: "branch",
                 text: `Rewound to an earlier decision — this is branch ${s.branches + 1}. The board is back to how it was then${s.mode === "live" ? "; anything already done on GitHub stays done" : ""}.` }] };
    case "error":
      return { ...s, error: a.message, streaming: false, status: s.status === "starting" || s.status === "streaming" ? "idle" : s.status };
    case "restore":
      return { ...s, threadId: a.threadId, title: a.title, goal: a.state.goal || "", missionId: a.state.mission_id,
               repo: a.state.repo || a.state.world?.repo?.full_name || "", mode: a.state.world?.mode || "fixture",
               canWrite: !!a.state.world?.can_write, feed: a.feed, board: a.state.world, pending: a.state.pending,
               status: a.state.status, report: a.state.report, autonomy: a.state.autonomy, streaming: false };
    case "event": {
      const ev = a.event;
      const feed = s.feed.slice();
      switch (ev.type) {
        case "thread":
          return { ...s, threadId: ev.thread_id, missionId: ev.mission_id, title: ev.title, repo: ev.repo || s.repo,
                   mode: ev.mode || s.mode, canWrite: ev.can_write ?? s.canWrite, autonomy: ev.autonomy || s.autonomy };
        case "token": {
          const cur = lastNarration(feed);
          if (cur && cur.kind === "narration") feed[feed.length - 1] = { ...cur, text: cur.text + ev.content };
          else feed.push({ kind: "narration", id: uid(), text: ev.content, streaming: true });
          return { ...s, feed };
        }
        case "tool_calls": {
          const cur = lastNarration(feed);
          if (cur && cur.kind === "narration") feed[feed.length - 1] = { ...cur, streaming: false };
          feed.push({ kind: "tools", id: uid(), calls: ev.calls.map((c: any) => ({ ...c, status: "running" as CallStatus })) });
          return { ...s, feed };
        }
        case "tool_result":
          return applyResult(feed, ev) ? { ...s, feed } : s;
        case "progress":
          if (ev.kind === "memory") feed.push({ kind: "system", id: uid(), tone: "memory", text: ev.message });
          return { ...s, feed };
        case "guardrail":
          feed.push({ kind: "system", id: uid(), tone: "warn",
                      text: ev.action === "redacted" ? `Guardrail: ${ev.count} piece${ev.count === 1 ? "" : "s"} of personal data were masked before the model saw them.`
                          : `Guardrail blocked a phrase: “${ev.phrase}”.` });
          return { ...s, feed };
        case "world_ops": {
          const seen = new Set(feed.flatMap((e) => (e.kind === "change" ? e.ops.map((o) => JSON.stringify(o)) : [])));
          const ops = ev.ops.filter((o: any) => o.op !== "create_label" && !seen.has(JSON.stringify(o)));
          if (ops.length) {
            // Consecutive changes read as one line of chips, not a column.
            const last = feed[feed.length - 1];
            if (last && last.kind === "change") feed[feed.length - 1] = { ...last, ops: [...last.ops, ...ops] };
            else feed.push({ kind: "change", id: uid(), ops });
          }
          return { ...s, feed };
        }
        case "report":
          feed.push({ kind: "report", id: uid(), report: ev.report });
          return { ...s, feed, report: ev.report };
        case "cancelled":
          feed.push({ kind: "system", id: uid(), tone: "info", text: ev.message });
          return { ...s, feed };
        case "error":
          feed.push({ kind: "system", id: uid(), tone: "error", text: ev.content });
          return { ...s, feed, streaming: false, status: "idle" };
        case "state": {
          const cur = lastNarration(feed);
          if (cur && cur.kind === "narration") feed[feed.length - 1] = { ...cur, streaming: false };
          const pendingIds = new Set(ev.pending.approvals.map((p: Approval) => p.tool_call_id));
          for (let i = feed.length - 1; i >= 0; i--) {
            const e = feed[i];
            if (e.kind !== "tools" || !e.calls.some((c) => c.status === "running")) continue;
            feed[i] = { ...e, calls: e.calls.map((c) => c.status === "running"
              ? { ...c, status: pendingIds.has(c.id) || c.name === "ask_user" ? "pending" : "ok" } : c) };
          }
          return { ...s, feed, board: ev.world, pending: ev.pending, status: ev.status, report: ev.report ?? s.report,
                   autonomy: ev.autonomy, canWrite: ev.world?.can_write ?? s.canWrite, mode: ev.world?.mode || s.mode,
                   streaming: false };
        }
        case "done":
          return { ...s, streaming: false };
        default:
          return s;
      }
    }
  }
  return s;
}

const STORE_KEY = "rs_thread";

export function useMission() {
  const [ui, dispatch] = useReducer(reduce, initial);
  const abort = useRef<AbortController | null>(null);

  const run = useCallback(async (path: string, body: Record<string, unknown> | null) => {
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    dispatch({ type: "stream", on: true });
    try {
      await stream(path, body, (ev) => dispatch({ type: "event", event: ev }), ctrl.signal);
      dispatch({ type: "stream", on: false });
    } catch (e: any) {
      if (e?.name === "AbortError") return;
      dispatch({ type: "error", message: describeError(e, e?.message || "Lost the connection to the backend.") });
    }
  }, []);

  const start = useCallback(async (goal: string, opts: { repo: string; missionId?: string | null; title: string;
                                                        userId: string | null; autonomy: string }) => {
    dispatch({ type: "reset", goal, title: opts.title, missionId: opts.missionId ?? null, repo: opts.repo, autonomy: opts.autonomy });
    await run("/missions/start", { repo: opts.repo, goal, mission_id: opts.missionId ?? null, user_id: opts.userId, autonomy: opts.autonomy });
  }, [run]);

  const decide = useCallback(async (decisions: Record<string, Decision>) => {
    if (!ui.threadId) return;
    const entries: Entry[] = [];
    for (const [id, d] of Object.entries(decisions)) {
      const approval = ui.pending.approvals.find((a) => a.interrupt_id === id);
      if (typeof d === "string") entries.push({ kind: "decision", id: uid(), tone: "answer", text: `You answered: ${d}` });
      else if (approval) {
        const what = describeCall(approval.name, approval.args, approval.risk?.preview);
        const text = d.type === "approve" ? `Approved · ${what}`
          : d.type === "reject" ? `Rejected · ${what}${d.message ? ` — “${d.message}”` : ""}`
          : d.type === "edit" ? `Edited, then approved · ${describeCall(d.edited_action.name, d.edited_action.args)}`
          : `Answered instead · “${d.message}”`;
        entries.push({ kind: "decision", id: uid(), tone: d.type, text });
      }
    }
    // A bulk decision reads as one line, not ten.
    const count = entries.length;
    let shown = entries;
    if (entries.length > 3) {
      const byTone = new Map<string, number>();
      for (const e of entries) if (e.kind === "decision") byTone.set(e.tone, (byTone.get(e.tone) || 0) + 1);
      shown = [...byTone.entries()].map(([tone, n]) => ({
        kind: "decision" as const, id: uid(), tone: tone as any,
        text: `${tone === "approve" ? "Approved" : tone === "reject" ? "Rejected" : tone === "edit" ? "Edited" : "Answered"} ${n} action${n === 1 ? "" : "s"} at once`,
      }));
    }
    dispatch({ type: "decided", entries: shown, count });
    await run(`/missions/${ui.threadId}/decide`, { decisions });
  }, [run, ui.threadId, ui.pending.approvals]);

  const followUp = useCallback(async (message: string) => {
    if (!ui.threadId) return;
    dispatch({ type: "decided", entries: [{ kind: "goal", id: uid(), text: message }], count: 0 });
    await run(`/missions/${ui.threadId}/continue`, { message });
  }, [run, ui.threadId]);

  const loadHistory = useCallback(async () => {
    if (!ui.threadId) return;
    const data = await getJSON(`/missions/${ui.threadId}/history`);
    dispatch({ type: "history", points: data.decision_points });
  }, [ui.threadId]);

  const fork = useCallback(async (checkpointId: string) => {
    if (!ui.threadId) return;
    dispatch({ type: "branch" });
    await run(`/missions/${ui.threadId}/fork`, { checkpoint_id: checkpointId });
  }, [run, ui.threadId]);

  const pause = useCallback(async () => {
    if (!ui.threadId) return;
    try { await postJSON(`/missions/${ui.threadId}/cancel`, {}); } catch { /* nothing in flight */ }
  }, [ui.threadId]);

  const clearError = useCallback(() => dispatch({ type: "error", message: null }), []);

  useEffect(() => {
    try {
      if (ui.threadId) localStorage.setItem(STORE_KEY, JSON.stringify({ threadId: ui.threadId, title: ui.title, repo: ui.repo }));
    } catch { /* storage blocked */ }
  }, [ui.threadId, ui.title, ui.repo]);

  const restore = useCallback(async (threadId: string, title: string) => {
    const [state, timeline] = await Promise.all([
      getJSON<MissionState>(`/missions/${threadId}`),
      getJSON<{ events: any[] }>(`/missions/${threadId}/timeline`),
    ]);
    const feed: Entry[] = [];
    const pendingIds = new Set(state.pending.approvals.map((p) => p.tool_call_id));
    for (const ev of timeline.events) {
      if (ev.type === "goal") feed.push({ kind: "goal", id: uid(), text: ev.content });
      else if (ev.type === "narration") feed.push({ kind: "narration", id: uid(), text: ev.content, streaming: false });
      else if (ev.type === "tool_calls") feed.push({ kind: "tools", id: uid(),
        calls: ev.calls.map((c: any) => ({ ...c, status: pendingIds.has(c.id) ? "pending" : "running" })) });
      else if (ev.type === "tool_result") applyResult(feed, ev);
    }
    for (const e of feed) if (e.kind === "tools") e.calls = e.calls.map((c) => c.status === "running" ? { ...c, status: "ok" } : c);
    if (state.report) feed.push({ kind: "report", id: uid(), report: state.report });
    dispatch({ type: "restore", state, feed, threadId, title });
  }, []);

  const leave = useCallback(() => {
    abort.current?.abort();
    try { localStorage.removeItem(STORE_KEY); } catch { /* ignore */ }
    dispatch({ type: "reset", goal: "", title: "", missionId: null, repo: "", autonomy: ui.autonomy });
    dispatch({ type: "error", message: null });
  }, [ui.autonomy]);

  return { ui, start, decide, followUp, loadHistory, fork, pause, restore, leave, clearError };
}

export function savedThread(): { threadId: string; title: string; repo: string } | null {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
