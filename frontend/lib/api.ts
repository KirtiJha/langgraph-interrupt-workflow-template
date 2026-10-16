"use client";

// Repo Steward API client: types, SSE reader, and the vocabulary that turns
// raw tool calls into human sentences.

import { apiHeaders, ensureOk } from "./modelSettings";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// --- Types (mirror backend/steward) --------------------------------------------
export interface Mission {
  id: string; emoji: string; title: string; goal: string; blurb: string; tags: string[]; approvals: number; accent: string;
}

export interface Label { name: string; color: string; description: string }

export interface Thread { author: string; body: string; created_at?: string; proposed?: boolean }

export interface Issue {
  number: number; title: string; body: string; state: string; state_reason?: string; author: string;
  author_association: string; labels: string[]; assignees: string[]; reviewers?: string[]; comments: number;
  created_at: string | null; updated_at: string | null; is_pr: boolean; draft: boolean; url: string;
  milestone: string | null; thread: Thread[]; by_agent?: boolean;
}

export interface RepoInfo {
  full_name: string; description: string; default_branch: string; stars: number; open_issues: number; url: string;
  owner: string; maintainer?: string | null; pushed_at: string | null;
}

export interface LedgerEntry { seq: number; op: string; number: number | null; summary: string; proposed: boolean; url: string; at: string }

export interface Board {
  repo: RepoInfo; labels: Label[]; issues: Issue[]; pulls: Issue[]; readme: string;
  mode: "live" | "fixture"; can_write: boolean; rate?: { remaining?: string; limit?: string }; ledger: LedgerEntry[];
}

export interface Inspection extends Omit<Board, "ledger" | "readme"> {
  token: "user" | "server" | null; memories: string[];
}

export interface Risk {
  level: "low" | "medium" | "high"; reasons: string[]; reversible: boolean; preview: any; asked: boolean;
  autonomy: string; observe?: boolean; jev?: { risky: boolean; confidence?: number; reason?: string; source: string };
}

export interface Approval {
  interrupt_id: string; tool_call_id: string; name: string; args: Record<string, any>; description: string;
  allowed: string[]; response_schema: any; risk: Risk | null;
}

export interface Question { interrupt_id: string; question: string; options: string[] }

export interface Report { summary: string; done: string[]; open_items: string[]; proposals: number }

export interface MissionState {
  type: "state";
  status: "awaiting_approval" | "awaiting_answer" | "running" | "completed" | "idle" | "paused";
  requires_input: boolean;
  pending: { approvals: Approval[]; question: Question | null };
  world: Board;
  report: Report | null;
  autonomy: string;
  goal: string | null;
  mission_id: string | null;
  repo: string | null;
  closing: string;
  checkpoint_id: string | null;
  step: number | null;
}

export interface DecisionPoint {
  checkpoint_id: string; step: number; created_at: string;
  approvals: { name: string; args: Record<string, any> }[]; question: string | null; ledger_len: number;
}

export type Decision =
  | { type: "approve" }
  | { type: "edit"; edited_action: { name: string; args: Record<string, any> } }
  | { type: "reject"; message: string }
  | { type: "respond"; message: string }
  | string;

// --- HTTP ---------------------------------------------------------------------
export async function stream(path: string, body: Record<string, unknown> | null, onEvent: (event: any) => void,
                             signal?: AbortSignal): Promise<void> {
  const res = await fetch(`${API_URL}${path}`, { method: "POST", headers: apiHeaders(), body: body ? JSON.stringify(body) : "{}", signal });
  await ensureOk(res);
  if (!res.body) throw new Error("No response body");
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const line = part.trim();
      if (line.startsWith("data: ")) {
        try { onEvent(JSON.parse(line.slice(6))); } catch { /* keep-alive */ }
      }
    }
  }
}

export async function getJSON<T = any>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { headers: apiHeaders() });
  await ensureOk(res);
  return res.json();
}

export async function postJSON<T = any>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { method: "POST", headers: apiHeaders(), body: JSON.stringify(body) });
  await ensureOk(res);
  return res.json();
}

// --- Vocabulary -----------------------------------------------------------------
export function fmtDate(iso?: string | null, opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" }) {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-US", opts);
}

export function daysAgo(iso?: string | null): number | null {
  if (!iso) return null;
  const d = new Date(iso).getTime();
  return isNaN(d) ? null : Math.max(0, Math.floor((Date.now() - d) / 86_400_000));
}

export function ageLabel(iso?: string | null): string {
  const n = daysAgo(iso);
  if (n == null) return "";
  if (n === 0) return "today";
  if (n === 1) return "yesterday";
  if (n < 30) return `${n}d ago`;
  if (n < 365) return `${Math.floor(n / 30)}mo ago`;
  return `${Math.floor(n / 365)}y ago`;
}

export const TOOL_LABELS: Record<string, { doing: string; icon: string }> = {
  list_issues: { doing: "Listing issues", icon: "list" },
  list_pulls: { doing: "Listing pull requests", icon: "git" },
  read_issue: { doing: "Reading a thread", icon: "book" },
  find_similar: { doing: "Checking for duplicates", icon: "search" },
  read_file: { doing: "Reading a file", icon: "file" },
  read_pull: { doing: "Reading a diff", icon: "diff" },
  release_context: { doing: "Reading commits since the last tag", icon: "tag" },
  ask_user: { doing: "Asking you", icon: "help" },
  remember: { doing: "Remembering", icon: "brain" },
  add_labels: { doing: "Labelling", icon: "tag" },
  remove_labels: { doing: "Removing labels", icon: "tag" },
  comment: { doing: "Commenting", icon: "message" },
  close_issue: { doing: "Closing", icon: "check" },
  reopen_issue: { doing: "Reopening", icon: "undo" },
  retitle: { doing: "Retitling", icon: "pencil" },
  create_issue: { doing: "Opening an issue", icon: "plus" },
  assign: { doing: "Assigning", icon: "user" },
  request_reviewers: { doing: "Requesting review", icon: "eye" },
  merge_pull: { doing: "Merging", icon: "git" },
  finish_mission: { doing: "Wrapping up", icon: "flag" },
};

export function describeCall(name: string, args: Record<string, any>, preview?: any): string {
  const a = args || {};
  const n = a.number != null ? `#${a.number}` : "";
  switch (name) {
    case "add_labels": return `Label ${n} ${(a.labels || []).join(", ")}`;
    case "remove_labels": return `Remove ${(a.labels || []).join(", ")} from ${n}`;
    case "comment": return `Comment on ${n}`;
    case "close_issue": return `Close ${n}${a.reason ? ` as ${String(a.reason).replace("_", " ")}` : ""}${a.note ? " with a note" : ""}`;
    case "reopen_issue": return `Reopen ${n}`;
    case "retitle": return `Retitle ${n}: “${a.title}”`;
    case "create_issue": return `Open an issue: “${a.title}”`;
    case "assign": return `Assign ${n} to ${(a.assignees || []).join(", ")}`;
    case "request_reviewers": return `Request review on ${n} from ${(a.reviewers || []).join(", ")}`;
    case "merge_pull": return `Merge ${n} (${a.method || "squash"})`;
    case "list_issues": return a.only && a.only !== "all" ? `List ${a.only} issues` : "List open issues";
    case "list_pulls": return "List open pull requests";
    case "read_issue": return `Read ${n}`;
    case "find_similar": return `Look for duplicates of ${n}`;
    case "read_file": return `Read ${a.path || "README.md"}`;
    case "read_pull": return `Read the diff of ${n}`;
    case "release_context": return "Read commits since the last tag";
    case "ask_user": return "Ask you a question";
    case "remember": return `Remember: ${a.note}`;
    case "finish_mission": return "Write the mission report";
    default: return TOOL_LABELS[name]?.doing || name.replace(/_/g, " ");
  }
}

/** Markdown checklist of everything in the ledger (for observe mode / sharing). */
export function ledgerToMarkdown(board: Board, title: string): string {
  const lines = board.ledger.map((l) => `- [${l.proposed ? " " : "x"}] ${l.summary}${l.url ? ` (${l.url})` : ""}`);
  return `## ${title} — ${board.repo.full_name}\n\n${lines.join("\n")}\n\n_Proposed by Repo Steward._`;
}
