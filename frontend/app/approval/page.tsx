"use client";

import { useState } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import {
  Send,
  Check,
  Pencil,
  X,
  Loader2,
  FileText,
  ArrowLeft,
  CheckCircle2,
} from "lucide-react";

// Backend API base URL — override with NEXT_PUBLIC_API_URL at build/run time.
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Status =
  | "idle"
  | "drafting"
  | "awaiting_review"
  | "sent"
  | "sent_with_unresolved_feedback";

interface ApprovalResponse {
  thread_id?: string;
  requires_input: boolean;
  draft: string;
  status: Status;
  final_output: string;
  revision_count: number;
}

export default function ApprovalPage() {
  const [task, setTask] = useState("");
  const [threadId, setThreadId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [revision, setRevision] = useState(0);
  const [finalOutput, setFinalOutput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Inline editors
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [rejecting, setRejecting] = useState(false);
  const [feedback, setFeedback] = useState("");

  const resetEditors = () => {
    setEditing(false);
    setRejecting(false);
    setFeedback("");
  };

  const applyResponse = (data: ApprovalResponse) => {
    setDraft(data.draft);
    setStatus(data.status);
    setRevision(data.revision_count);
    setFinalOutput(data.final_output);
    resetEditors();
  };

  const startDraft = async () => {
    if (!task.trim()) return;
    setLoading(true);
    setError(null);
    setFinalOutput("");
    try {
      const res = await fetch(`${API_URL}/approval/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ApprovalResponse = await res.json();
      setThreadId(data.thread_id ?? null);
      applyResponse(data);
    } catch (e) {
      setError("Could not start the workflow. Is the backend running on " + API_URL + "?");
    } finally {
      setLoading(false);
    }
  };

  const decide = async (
    action: "approve" | "edit" | "reject",
    extra: { content?: string; feedback?: string } = {}
  ) => {
    if (!threadId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_URL}/approval/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ thread_id: threadId, action, ...extra }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ApprovalResponse = await res.json();
      applyResponse(data);
    } catch (e) {
      setError("Could not submit your decision. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const isSent = status === "sent" || status === "sent_with_unresolved_feedback";
  const reviewing = status === "awaiting_review" && !isSent;

  const reset = () => {
    setThreadId(null);
    setTask("");
    setDraft("");
    setStatus("idle");
    setRevision(0);
    setFinalOutput("");
    resetEditors();
    setError(null);
  };

  return (
    <main className="min-h-screen bg-gradient-to-b from-gray-50 to-indigo-50/40 py-10 px-4">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <Link
            href="/"
            className="inline-flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-800 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" /> Research assistant
          </Link>
          <span className="text-xs font-medium text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-full px-3 py-1">
            Human-in-the-loop · Approve / Edit / Reject
          </span>
        </div>

        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <FileText className="w-6 h-6 text-indigo-600" /> Approval Workflow
        </h1>
        <p className="text-gray-600 mt-1 mb-6 text-sm">
          The AI drafts content for your task, then pauses. You approve it,
          edit it, or reject it with feedback — and it redrafts.
        </p>

        {/* Task input */}
        <div className="bg-white border border-gray-100 rounded-xl shadow-soft p-4 mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            What should the AI draft?
          </label>
          <div className="flex gap-2">
            <input
              value={task}
              onChange={(e) => setTask(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !threadId && startDraft()}
              disabled={!!threadId && !isSent}
              placeholder="e.g. A friendly email apologizing for a shipping delay"
              className="flex-1 rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300 disabled:bg-gray-50"
            />
            {!threadId || isSent ? (
              <button
                onClick={isSent ? reset : startDraft}
                disabled={loading || (!isSent && !task.trim())}
                className="inline-flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg px-4 py-2 text-sm font-medium transition-colors"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
                {isSent ? "New draft" : "Draft it"}
              </button>
            ) : null}
          </div>
        </div>

        {error && (
          <div className="mb-6 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg p-3">
            {error}
          </div>
        )}

        {/* Draft + review actions */}
        {draft && !isSent && (
          <div className="bg-white border border-gray-100 rounded-xl shadow-soft p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-semibold text-gray-900">Draft</h2>
              {revision > 0 && (
                <span className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-2.5 py-0.5">
                  Revision {revision}
                </span>
              )}
            </div>

            <div className="prose prose-sm max-w-none bg-gray-50 border border-gray-100 rounded-lg p-4 text-gray-800">
              <ReactMarkdown>{draft}</ReactMarkdown>
            </div>

            {/* Edit mode */}
            {editing && (
              <div className="mt-4">
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Edit the draft, then send your version:
                </label>
                <textarea
                  value={editText}
                  onChange={(e) => setEditText(e.target.value)}
                  rows={6}
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
                />
                <div className="flex gap-2 mt-2">
                  <button
                    onClick={() => decide("edit", { content: editText })}
                    disabled={loading}
                    className="inline-flex items-center gap-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg px-3 py-1.5 text-sm font-medium"
                  >
                    <Check className="w-4 h-4" /> Send edited version
                  </button>
                  <button
                    onClick={() => setEditing(false)}
                    className="text-sm text-gray-500 hover:text-gray-800 px-2"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {/* Reject mode */}
            {rejecting && (
              <div className="mt-4">
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  What should change? The AI will redraft using your feedback:
                </label>
                <textarea
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  rows={3}
                  placeholder="e.g. Make it shorter and warmer in tone"
                  className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-rose-300"
                />
                <div className="flex gap-2 mt-2">
                  <button
                    onClick={() => decide("reject", { feedback })}
                    disabled={loading || !feedback.trim()}
                    className="inline-flex items-center gap-1.5 bg-rose-600 hover:bg-rose-700 disabled:opacity-50 text-white rounded-lg px-3 py-1.5 text-sm font-medium"
                  >
                    <X className="w-4 h-4" /> Request changes
                  </button>
                  <button
                    onClick={() => setRejecting(false)}
                    className="text-sm text-gray-500 hover:text-gray-800 px-2"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {/* Primary action bar */}
            {reviewing && !editing && !rejecting && (
              <div className="flex flex-wrap gap-2 mt-4">
                <button
                  onClick={() => decide("approve")}
                  disabled={loading}
                  className="inline-flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg px-4 py-2 text-sm font-medium"
                >
                  {loading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Check className="w-4 h-4" />
                  )}
                  Approve & send
                </button>
                <button
                  onClick={() => {
                    setEditText(draft);
                    setEditing(true);
                  }}
                  disabled={loading}
                  className="inline-flex items-center gap-1.5 bg-white border border-gray-200 hover:bg-gray-50 text-gray-800 rounded-lg px-4 py-2 text-sm font-medium"
                >
                  <Pencil className="w-4 h-4" /> Edit
                </button>
                <button
                  onClick={() => setRejecting(true)}
                  disabled={loading}
                  className="inline-flex items-center gap-1.5 bg-white border border-gray-200 hover:bg-gray-50 text-gray-800 rounded-lg px-4 py-2 text-sm font-medium"
                >
                  <X className="w-4 h-4" /> Reject
                </button>
              </div>
            )}
          </div>
        )}

        {/* Sent confirmation */}
        {isSent && (
          <div className="bg-white border border-emerald-100 rounded-xl shadow-soft p-5">
            <div className="flex items-center gap-2 text-emerald-700 font-semibold mb-3">
              <CheckCircle2 className="w-5 h-5" />
              {status === "sent_with_unresolved_feedback"
                ? "Sent (revision limit reached)"
                : "Approved & sent"}
            </div>
            <div className="prose prose-sm max-w-none bg-emerald-50/50 border border-emerald-100 rounded-lg p-4 text-gray-800">
              <ReactMarkdown>{finalOutput}</ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
