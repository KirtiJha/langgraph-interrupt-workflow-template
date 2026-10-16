"use client";

// The mission state machine: turns the backend's SSE events into a feed, the
// live world, pending decisions and a status — and exposes the actions.

import { useCallback, useEffect, useReducer, useRef } from "react";
import {
  Approval, Decision, DecisionPoint, MissionState, Question, Report, World,
  getJSON, postJSON, stream, describeCall,
} from "./api";
import { describeError } from "./modelSettings";

export type CallStatus = "running" | "pending" | "ok" | "rejected" | "edited" | "responded";

export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, any>;
  status: CallStatus;
  result?: string;
}

export type Entry =
  | { kind: "goal"; id: string; text: string }
  | { kind: "narration"; id: string; text: string; streaming: boolean }
  | { kind: "tools"; id: string; calls: ToolCall[] }
  | { kind: "options"; id: string; optionsKind: string; options: any[] }
  | { kind: "change"; id: string; ops: any[] }
  | { kind: "decision"; id: string; text: string; tone: "approve" | "reject" | "edit" | "respond" | "answer" }
  | { kind: "report"; id: string; report: Report }
  | { kind: "system"; id: string; text: string; tone?: "info" | "warn" | "error" | "memory" | "branch" };

export interface MissionUI {
  threadId: string | null;
  title: string;
  missionId: string | null;
  goal: string;
  feed: Entry[];
  world: World | null;
  startBalance: number | null;
  pending: { approvals: Approval[]; question: Question | null };
  status: MissionState["status"] | "starting" | "streaming";
  streaming: boolean;
  report: Report | null;
  autonomy: string;
  askAbove: number;
  decisionsMade: number;
  branches: number;
  history: DecisionPoint[];
  error: string | null;
}

const initial: MissionUI = {
  threadId: null, title: "", missionId: null, goal: "", feed: [], world: null, startBalance: null,
  pending: { approvals: [], question: null }, status: "idle", streaming: false, report: null,
  autonomy: "careful", askAbove: 100, decisionsMade: 0, branches: 1, history: [], error: null,
};

let seq = 0;
const uid = () => `e${++seq}`;

type Action =
  | { type: "reset"; goal: string; title: string; missionId: string | null; autonomy: string; askAbove: number }
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

function reduce(s: MissionUI, a: Action): MissionUI {
  switch (a.type) {
    case "reset":
      return { ...initial, goal: a.goal, title: a.title, missionId: a.missionId, autonomy: a.autonomy,
               askAbove: a.askAbove, status: "starting", streaming: true,
               feed: [{ kind: "goal", id: uid(), text: a.goal }] };
    case "stream":
      return { ...s, streaming: a.on, status: a.on && s.status === "idle" ? "streaming" : s.status };
    case "decided":
      return { ...s, feed: [...s.feed, ...a.entries], decisionsMade: s.decisionsMade + a.count,
               pending: { approvals: [], question: null }, streaming: true, status: "streaming" };
    case "history":
      return { ...s, history: a.points };
    case "branch":
      return { ...s, branches: s.branches + 1, streaming: true, status: "streaming",
               pending: { approvals: [], question: null },
               feed: [...s.feed, { kind: "system", id: uid(), tone: "branch",
                                   text: `Rewound to an earlier decision — this is branch ${s.branches + 1}. The world is back to how it was then.` }] };
    case "error":
      return { ...s, error: a.message, streaming: false,
               status: s.status === "starting" || s.status === "streaming" ? "idle" : s.status };
    case "restore":
      return { ...s, threadId: a.threadId, title: a.title, goal: a.state.goal || "", missionId: a.state.mission_id,
               feed: a.feed, world: a.state.world, startBalance: 3240, pending: a.state.pending,
               status: a.state.status, report: a.state.report, autonomy: a.state.autonomy,
               askAbove: a.state.ask_above, streaming: false };
    case "event": {
      const ev = a.event;
      const feed = s.feed.slice();
      switch (ev.type) {
        case "thread":
          return { ...s, threadId: ev.thread_id, missionId: ev.mission_id, title: ev.title };
        case "token": {
          const cur = lastNarration(feed);
          if (cur && cur.kind === "narration") feed[feed.length - 1] = { ...cur, text: cur.text + ev.content };
          else feed.push({ kind: "narration", id: uid(), text: ev.content, streaming: true });
          return { ...s, feed };
        }
        case "tool_calls": {
          const cur = lastNarration(feed);
          if (cur && cur.kind === "narration") feed[feed.length - 1] = { ...cur, streaming: false };
          feed.push({ kind: "tools", id: uid(),
                      calls: ev.calls.map((c: any) => ({ ...c, status: "running" as CallStatus })) });
          return { ...s, feed };
        }
        case "tool_result": {
          for (let i = feed.length - 1; i >= 0; i--) {
            const e = feed[i];
            if (e.kind !== "tools") continue;
            const idx = e.calls.findIndex((c) => c.id === ev.id);
            if (idx < 0) continue;
            if (e.calls[idx].status === "ok" || e.calls[idx].status === "edited") return s; // duplicate on resume
            const calls = e.calls.slice();
            const status: CallStatus = ev.status === "rejected" ? "rejected" : ev.status === "edited" ? "edited"
              : calls[idx].status === "responded" ? "responded" : "ok";
            calls[idx] = { ...calls[idx], status, result: ev.content };
            feed[i] = { ...e, calls };
            break;
          }
          return { ...s, feed };
        }
        case "progress":
          if (ev.options && ev.kind) feed.push({ kind: "options", id: uid(), optionsKind: ev.kind, options: ev.options });
          else if (ev.kind === "memory") feed.push({ kind: "system", id: uid(), tone: "memory", text: ev.message });
          return { ...s, feed };
        case "guardrail":
          feed.push({ kind: "system", id: uid(), tone: "warn",
                      text: ev.action === "redacted" ? `Guardrail: ${ev.count} piece${ev.count === 1 ? "" : "s"} of personal data were masked before the model saw them.`
                          : `Guardrail blocked a phrase: “${ev.phrase}”.` });
          return { ...s, feed };
        case "world_ops": {
          // A resume re-delivers the node's earlier writes; show each change once.
          const seen = new Set(feed.flatMap((e) => (e.kind === "change" ? e.ops.map((o) => JSON.stringify(o)) : [])));
          const ops = ev.ops.filter((o: any) => !seen.has(JSON.stringify(o)));
          if (ops.length) feed.push({ kind: "change", id: uid(), ops });
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
          // Calls still running when the mission paused are the ones awaiting you.
          const pendingIds = new Set(ev.pending.approvals.map((p: Approval) => p.tool_call_id));
          for (let i = feed.length - 1; i >= 0; i--) {
            const e = feed[i];
            if (e.kind !== "tools") continue;
            if (e.calls.some((c) => c.status === "running")) {
              feed[i] = { ...e, calls: e.calls.map((c) => c.status === "running"
                ? { ...c, status: pendingIds.has(c.id) || c.name === "ask_user" ? "pending" : "ok" } : c) };
            }
          }
          return { ...s, feed, world: ev.world, startBalance: s.startBalance ?? ev.world?.wallet?.balance ?? null,
                   pending: ev.pending, status: ev.status, report: ev.report ?? s.report,
                   autonomy: ev.autonomy, askAbove: ev.ask_above, streaming: false };
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

const STORE_KEY = "mc_thread";

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

  const start = useCallback(async (goal: string, opts: { missionId?: string | null; title: string; userId: string | null;
                                                        autonomy: string; askAbove: number }) => {
    dispatch({ type: "reset", goal, title: opts.title, missionId: opts.missionId ?? null, autonomy: opts.autonomy,
               askAbove: opts.askAbove });
    await run("/missions/start", { goal, mission_id: opts.missionId ?? null, user_id: opts.userId,
                                   autonomy: opts.autonomy, ask_above: opts.askAbove });
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
          : d.type === "edit" ? `Edited, then approved · ${describeCall(d.edited_action.name, d.edited_action.args, approval.risk?.preview)}`
          : `Answered instead · “${d.message}”`;
        entries.push({ kind: "decision", id: uid(), tone: d.type, text });
      }
    }
    dispatch({ type: "decided", entries, count: entries.length });
    await run(`/missions/${ui.threadId}/decide`, { decisions });
  }, [run, ui.threadId, ui.pending.approvals]);

  const followUp = useCallback(async (message: string) => {
    if (!ui.threadId) return;
    dispatch({ type: "event", event: { type: "goal_followup" } });
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

  // Remember the open mission so a reload (or a second tab) can pick it up.
  useEffect(() => {
    try {
      if (ui.threadId) localStorage.setItem(STORE_KEY, JSON.stringify({ threadId: ui.threadId, title: ui.title }));
    } catch { /* storage blocked */ }
  }, [ui.threadId, ui.title]);

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
      else if (ev.type === "tool_result") {
        for (let i = feed.length - 1; i >= 0; i--) {
          const e = feed[i];
          if (e.kind !== "tools") continue;
          const idx = e.calls.findIndex((c) => c.id === ev.id);
          if (idx < 0) continue;
          const calls = e.calls.slice();
          calls[idx] = { ...calls[idx], status: ev.status === "rejected" ? "rejected" : ev.status === "edited" ? "edited" : "ok", result: ev.content };
          feed[i] = { ...e, calls };
          break;
        }
      }
    }
    for (const e of feed) if (e.kind === "tools") e.calls = e.calls.map((c) => c.status === "running" ? { ...c, status: "ok" } : c);
    if (state.report) feed.push({ kind: "report", id: uid(), report: state.report });
    dispatch({ type: "restore", state, feed, threadId, title });
  }, []);

  const leave = useCallback(() => {
    abort.current?.abort();
    try { localStorage.removeItem(STORE_KEY); } catch { /* ignore */ }
    dispatch({ type: "reset", goal: "", title: "", missionId: null, autonomy: ui.autonomy, askAbove: ui.askAbove });
    dispatch({ type: "error", message: null });
  }, [ui.autonomy, ui.askAbove]);

  return { ui, start, decide, followUp, loadHistory, fork, pause, restore, leave, clearError };
}

export function savedThread(): { threadId: string; title: string } | null {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}
