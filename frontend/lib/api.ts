"use client";

// Mission Control API client: types, SSE reader, and the tool vocabulary the
// UI uses to turn raw tool calls into human sentences.

import { apiHeaders, ensureOk } from "./modelSettings";

export const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// --- Types (mirror backend/mission) ------------------------------------------
export interface Mission {
  id: string;
  emoji: string;
  title: string;
  goal: string;
  blurb: string;
  tags: string[];
  approvals: number;
  accent: string;
}

export interface Email {
  id: string; from: string; from_name: string; subject: string; date: string;
  unread: boolean; urgent: boolean; body: string; replied?: boolean;
}
export interface CalendarEvent {
  id: string; title: string; start: string; end: string; location: string; attendees: string[]; source: string;
}
export interface Transaction {
  id: string; date: string; payee: string; amount: number; category: string; memo?: string; by_agent?: boolean;
}
export interface Subscription {
  id: string; name: string; price: number; cycle: string; last_used_days: number; status: string;
}
export interface Booking {
  id: string; kind: string; vendor: string; date: string; details: string; amount: number;
  refundable: boolean; status: string; confirmation: string;
}
export interface World {
  today: string;
  owner: { name: string; email: string; city: string };
  wallet: { currency: string; balance: number; transactions: Transaction[] };
  calendar: CalendarEvent[];
  inbox: Email[];
  sent: { id: string; to: string[]; subject: string; body: string; date: string }[];
  contacts: { id: string; name: string; email: string; group: string; relation: string }[];
  subscriptions: Subscription[];
  bookings: Booking[];
  ledger: { seq: number; op: string; summary: string }[];
}

export interface Risk {
  level: "low" | "medium" | "high";
  reasons: string[];
  reversible: boolean;
  amount: number;
  preview: any;
  asked: boolean;
  autonomy: string;
  jev?: { risky: boolean; confidence?: number; reason?: string; source: string };
}

export interface Approval {
  interrupt_id: string;
  tool_call_id: string;
  name: string;
  args: Record<string, any>;
  description: string;
  allowed: string[];
  response_schema: any;
  risk: Risk | null;
}

export interface Question { interrupt_id: string; question: string; options: string[] }

export interface Report { summary: string; done: string[]; open_items: string[]; spent: number }

export interface MissionState {
  type: "state";
  status: "awaiting_approval" | "awaiting_answer" | "running" | "completed" | "idle" | "paused";
  requires_input: boolean;
  pending: { approvals: Approval[]; question: Question | null };
  world: World;
  report: Report | null;
  autonomy: string;
  ask_above: number;
  goal: string | null;
  mission_id: string | null;
  closing: string;
  checkpoint_id: string | null;
  step: number | null;
}

export interface DecisionPoint {
  checkpoint_id: string;
  step: number;
  created_at: string;
  approvals: { name: string; args: Record<string, any> }[];
  question: string | null;
  balance: number;
  ledger_len: number;
}

export type Decision =
  | { type: "approve" }
  | { type: "edit"; edited_action: { name: string; args: Record<string, any> } }
  | { type: "reject"; message: string }
  | { type: "respond"; message: string }
  | string; // an answer to a question

// --- SSE ---------------------------------------------------------------------
export async function stream(
  path: string,
  body: Record<string, unknown> | null,
  onEvent: (event: any) => void,
  signal?: AbortSignal
): Promise<void> {
  const res = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: apiHeaders(),
    body: body ? JSON.stringify(body) : "{}",
    signal,
  });
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
        try {
          onEvent(JSON.parse(line.slice(6)));
        } catch {
          /* keep-alive / partial */
        }
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

// --- Vocabulary ---------------------------------------------------------------
export const money = (n: number, digits = 0) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: digits, minimumFractionDigits: digits });

export function fmtDate(iso?: string, opts: Intl.DateTimeFormatOptions = { weekday: "short", month: "short", day: "numeric" }) {
  if (!iso) return "";
  const d = new Date(iso.length <= 10 ? `${iso}T12:00` : iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleDateString("en-US", opts);
}
export function fmtTime(iso?: string) {
  if (!iso || iso.length <= 10) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "" : d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export const TOOL_LABELS: Record<string, { doing: string; done: string; icon: string }> = {
  read_inbox: { doing: "Reading your inbox", done: "Read inbox", icon: "inbox" },
  read_calendar: { doing: "Checking your calendar", done: "Checked calendar", icon: "calendar" },
  check_wallet: { doing: "Checking your wallet", done: "Checked wallet", icon: "wallet" },
  list_contacts: { doing: "Looking up contacts", done: "Looked up contacts", icon: "users" },
  list_subscriptions: { doing: "Auditing subscriptions", done: "Audited subscriptions", icon: "repeat" },
  search_restaurants: { doing: "Searching restaurants", done: "Compared restaurants", icon: "search" },
  search_flights: { doing: "Searching flights", done: "Compared flights", icon: "plane" },
  search_hotels: { doing: "Searching hotels", done: "Compared hotels", icon: "bed" },
  get_quotes: { doing: "Getting quotes", done: "Compared quotes", icon: "clipboard" },
  ask_user: { doing: "Asking you", done: "Asked you", icon: "help" },
  remember: { doing: "Remembering", done: "Remembered", icon: "brain" },
  send_email: { doing: "Sending email", done: "Sent email", icon: "mail" },
  archive_emails: { doing: "Archiving emails", done: "Archived emails", icon: "archive" },
  add_calendar_event: { doing: "Adding to calendar", done: "Added to calendar", icon: "calendar" },
  pay: { doing: "Paying", done: "Paid", icon: "wallet" },
  book: { doing: "Booking", done: "Booked", icon: "ticket" },
  cancel_subscription: { doing: "Cancelling", done: "Cancelled", icon: "ban" },
  finish_mission: { doing: "Wrapping up", done: "Mission report", icon: "flag" },
};

/** One human line for a tool call, e.g. "Book Olive & Fig · $120 deposit". */
export function describeCall(name: string, args: Record<string, any>, preview?: any): string {
  const a = args || {};
  switch (name) {
    case "book":
      return `Book ${a.vendor}${a.amount ? ` · ${money(a.amount)}` : ""}${a.kind === "restaurant" && a.amount ? " deposit" : ""}`;
    case "pay":
      return `Pay ${money(a.amount)} to ${a.payee}`;
    case "send_email": {
      const n = (a.to || []).length;
      return `Email ${n === 1 ? a.to[0] : `${n} people`}: “${a.subject}”`;
    }
    case "add_calendar_event":
      return `Add “${a.title}” to your calendar${(a.attendees || []).length ? ` + invite ${a.attendees.length}` : ""}`;
    case "archive_emails":
      return `Archive ${(a.ids || []).length} email${(a.ids || []).length === 1 ? "" : "s"}`;
    case "cancel_subscription":
      return `Cancel ${preview?.name || a.id}`;
    case "search_restaurants":
      return `Search restaurants for ${a.party_size}${a.vegetarian ? " · vegetarian" : ""}`;
    case "search_flights":
      return `Search flights to ${a.destination}`;
    case "search_hotels":
      return `Search hotels in ${a.city}`;
    case "get_quotes":
      return `Get ${a.service} quotes`;
    case "list_contacts":
      return a.group ? `Look up ${a.group} contacts` : "Look up contacts";
    case "read_calendar":
      return `Check the next ${a.days || 45} days`;
    case "ask_user":
      return "Ask you a question";
    case "remember":
      return `Remember: ${a.note}`;
    case "finish_mission":
      return "Write the mission report";
    default:
      return TOOL_LABELS[name]?.doing || name.replace(/_/g, " ");
  }
}
