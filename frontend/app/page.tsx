"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import {
  Send,
  Bot,
  User,
  Loader2,
  Brain,
  Search,
  FileText,
  CheckCircle,
  MessageSquare,
  Settings,
  AlertCircle,
  History,
  Clock,
  ShieldCheck,
  ShieldAlert,
  ListChecks,
  Layers,
} from "lucide-react";

interface Message {
  role: "user" | "assistant" | "system" | "choice";
  content: string;
  timestamp: Date;
  choiceType?: string; // For choice messages, indicates what type of choice it was
}

interface InterruptData {
  type: string;
  message: string;
  question: string;
  options: Record<string, string> | string[];
  [key: string]: any;
}

interface ChatState {
  user_query: string;
  research_plan: string;
  research_results: string[];
  analysis: string;
  final_response: string;
  current_step: string;
  requires_user_input: boolean;
  interrupt_data: InterruptData | null;
  conversation_history: Message[];
}

const STEP_DESCRIPTIONS = {
  planning: "Planning research strategy",
  awaiting_approval: "Waiting for research approval",
  information_gathering: "Gathering information",
  research_direction_check: "Refining research direction",
  refining_research: "Refining research direction",
  analysis: "Analyzing information",
  format_selection: "Selecting response format",
  response_formatting: "Formatting response",
  completed: "Research completed",
};

const STEP_ICONS = {
  planning: Search,
  awaiting_approval: AlertCircle,
  information_gathering: FileText,
  refining_research: Settings,
  analysis: Brain,
  response_formatting: MessageSquare,
  completed: CheckCircle,
};

// Backend API base URL — override with NEXT_PUBLIC_API_URL at build/run time.
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function ChatInterface() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [chatState, setChatState] = useState<ChatState | null>(null);
  const [currentStep, setCurrentStep] = useState<string>("idle");
  const [interruptData, setInterruptData] = useState<InterruptData | null>(
    null
  );
  // Feature A: live progress from the parallel sub-researchers.
  const [progress, setProgress] = useState<string[]>([]);
  // Feature B: a stable id so the backend can remember this user across sessions.
  const [userId, setUserId] = useState<string | null>(null);
  // Feature C: time-travel checkpoints + the checkpoint we're forking from.
  const [history, setHistory] = useState<any[]>([]);
  const [showHistory, setShowHistory] = useState(false);
  const [forkCheckpoint, setForkCheckpoint] = useState<string | null>(null);
  // Which backend engine drives the conversation.
  const [engine, setEngine] = useState<"workflow" | "agent" | "deep">(
    "workflow"
  );
  // Agent tool-approval editor state (lifted out of the card component).
  const [agentEditing, setAgentEditing] = useState(false);
  const [agentRejecting, setAgentRejecting] = useState(false);
  const [agentResponding, setAgentResponding] = useState(false);
  const [agentArgsText, setAgentArgsText] = useState("");
  const [agentArgs, setAgentArgs] = useState<Record<string, string>>({});
  const [agentFeedback, setAgentFeedback] = useState("");
  const [agentResponse, setAgentResponse] = useState("");
  // Guardrail signals (PII redaction / blocklist) emitted by the agent engine.
  const [guardrailNotice, setGuardrailNotice] = useState<{
    action: string;
    count?: number;
    phrase?: string;
  } | null>(null);
  // Structured output (ResearchSummary) when AGENT_STRUCTURED_OUTPUT is enabled.
  const [structuredResponse, setStructuredResponse] = useState<any | null>(null);
  // Active backend features (from /capabilities) shown as header status badges.
  const [capabilities, setCapabilities] = useState<any | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Persist a user id in localStorage to enable cross-session memory.
  useEffect(() => {
    let id = localStorage.getItem("lg_user_id");
    if (!id) {
      id = `user-${Math.random().toString(36).slice(2, 10)}`;
      localStorage.setItem("lg_user_id", id);
    }
    setUserId(id);
  }, []);

  // Load which optional backend features are active (for the status strip).
  useEffect(() => {
    fetch(`${API_URL}/capabilities`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => data && setCapabilities(data))
      .catch(() => {
        /* backend not up yet — the strip simply stays hidden */
      });
  }, []);

  // Map a pending interrupt node / message to its choice options.
  const optionsForInterrupt = (message: string): string[] => {
    if (
      message.includes("Research Direction") ||
      message.includes("explore any specific angle")
    ) {
      return ["technical", "practical", "recent", "comparative", "continue"];
    }
    if (
      message.includes("Choose Response Format") ||
      message.includes("presentation style")
    ) {
      return [
        "comprehensive",
        "executive",
        "structured",
        "conversational",
        "bullet_points",
      ];
    }
    return ["proceed", "simplified", "focused", "cancel"];
  };

  const optionsForNode = (node: string): string[] => {
    if (node === "research_direction_interrupt")
      return ["technical", "practical", "recent", "comparative", "continue"];
    if (node === "format_selection_interrupt")
      return [
        "comprehensive",
        "executive",
        "structured",
        "conversational",
        "bullet_points",
      ];
    return ["proceed", "simplified", "focused", "cancel"];
  };

  // Parse a fetch-based SSE stream and dispatch each JSON event.
  const consumeStream = async (
    path: string,
    body: Record<string, unknown>,
    onEvent: (data: any) => void
  ) => {
    const res = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
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
            /* ignore keep-alives / partials */
          }
        }
      }
    }
  };

  const addMessage = (
    role: "user" | "assistant" | "system" | "choice",
    content: string,
    choiceType?: string
  ) => {
    const newMessage: Message = {
      role,
      content,
      timestamp: new Date(),
      choiceType,
    };
    setMessages((prev) => [...prev, newMessage]);
  };

  const addChoiceMessage = (choice: string, choiceType: string) => {
    // Create more descriptive labels for the choice display
    const getChoiceDisplay = (opt: string, type: string) => {
      const labels: { [key: string]: string } = {
        // Research planning options
        proceed: "Full comprehensive research",
        simplified: "Quick overview with key points",
        focused: "Targeted research on specific aspects",
        cancel: "Stop the research process",
        // Research direction options
        technical: "Deep dive into technical details",
        practical: "Real-world applications and use cases",
        recent: "Latest developments and trends",
        comparative: "Compare different approaches",
        continue: "General comprehensive analysis",
        continue_context: "Build on previous conversation",
        // Response format options
        comprehensive: "Detailed analysis with examples and explanations",
        executive: "Concise summary with key insights and recommendations",
        structured: "Clear headings, sections, and bullet points",
        conversational: "Natural, friendly tone with explanations",
        bullet_points: "Quick reference format with organized lists",
      };
      return labels[opt] || opt;
    };

    const displayText = getChoiceDisplay(choice, choiceType);
    addMessage("choice", displayText, choiceType);
  };

  const startChat = async (message: string) => {
    setIsLoading(true);
    addMessage("user", message);

    try {
      const response = await fetch(`${API_URL}/start`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message, user_id: userId }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setThreadId(data.thread_id);
      setChatState(data.state);
      setCurrentStep(data.state.current_step);

      if (data.requires_input && data.interrupt_message) {
        const options = optionsForInterrupt(data.interrupt_message);

        // Create interrupt data structure
        const interruptData = {
          type: "user_input",
          message: data.interrupt_message,
          question: data.interrupt_message,
          options: options,
        };
        setInterruptData(interruptData);
        // Don't add system message - only show the interrupt card
      } else if (data.state.final_response) {
        addMessage("assistant", data.state.final_response);
      }
    } catch (error) {
      console.error("Error starting chat:", error);
      addMessage(
        "system",
        "Sorry, there was an error starting the conversation. Please try again."
      );
    } finally {
      setIsLoading(false);
    }
  };

  // Unified resume: streams progress (parallel research), tokens (final answer),
  // and a closing state event. `fork` resumes from a past checkpoint (time travel).
  const runResume = async (choice: string, fork?: string) => {
    if (!threadId) return;

    setIsLoading(true);
    setInterruptData(null);
    setProgress([]);

    let assistantMessage = "";
    let assistantAdded = false;

    const path = fork ? "/fork" : "/stream";
    const body = fork
      ? { thread_id: threadId, checkpoint_id: fork, choice }
      : { thread_id: threadId, choice };

    try {
      await consumeStream(path, body, (data) => {
        if (data.type === "progress") {
          setIsLoading(false);
          setProgress((prev) => [...prev, data.message || data.phase || "…"]);
        } else if (data.type === "content" && !data.done) {
          setIsLoading(false);
          if (!assistantAdded) {
            addMessage("assistant", "");
            assistantAdded = true;
          }
          assistantMessage += data.content;
          setMessages((prev) => {
            const next = [...prev];
            const last = next.length - 1;
            if (last >= 0 && next[last].role === "assistant") {
              next[last] = { ...next[last], content: assistantMessage };
            }
            return next;
          });
        } else if (data.type === "state") {
          setProgress([]);
          setCurrentStep(data.current_step || "idle");
          setChatState((prev) => ({
            ...(prev as ChatState),
            current_step: data.current_step,
            research_results: data.research_results || [],
            final_response: data.final_response || "",
          }));
          if (data.requires_input && data.interrupt_message) {
            setInterruptData({
              type: "user_input",
              message: data.interrupt_message,
              question: data.interrupt_message,
              options: optionsForInterrupt(data.interrupt_message),
            });
          } else if (data.final_response && !assistantAdded) {
            addMessage("assistant", data.final_response);
          }
        }
      });
    } catch (error) {
      console.error("Error resuming chat:", error);
      addMessage(
        "system",
        "Sorry, there was an error processing your response. Please try again."
      );
    } finally {
      setIsLoading(false);
    }
  };

  // Feature C: load checkpoint history for the current thread.
  const loadHistory = async () => {
    if (!threadId) return;
    try {
      const res = await fetch(`${API_URL}/history/${threadId}`);
      const data = await res.json();
      setHistory(data.checkpoints || []);
      setShowHistory(true);
    } catch (error) {
      console.error("Error loading history:", error);
    }
  };

  // Feature C: rewind to a past interrupt and re-open its options to choose anew.
  const rewindTo = (checkpoint: any) => {
    const node = (checkpoint.next && checkpoint.next[0]) || "";
    setForkCheckpoint(checkpoint.checkpoint_id);
    setShowHistory(false);
    setInterruptData({
      type: "user_input",
      message: `Rewound to an earlier step (${checkpoint.current_step || node}). Pick a different path to fork from here.`,
      question: "Choose a different path",
      options: optionsForNode(node),
    });
  };

  // ── Agent engine (create_agent + HITL middleware) ──────────────────────────
  // Shared SSE handler for both /agent/start and /agent/decide.
  const consumeAgentStream = async (
    path: string,
    body: Record<string, unknown>
  ) => {
    setIsLoading(true);
    setInterruptData(null);
    setProgress([]);
    setGuardrailNotice(null);
    setStructuredResponse(null);
    let assistantMessage = "";
    let assistantAdded = false;

    try {
      await consumeStream(path, body, (data) => {
        if (data.type === "thread") {
          setThreadId(data.thread_id);
        } else if (data.type === "guardrail") {
          // Safety middleware fired: PII was redacted or input was blocked.
          setGuardrailNotice({
            action: data.action,
            count: data.count,
            phrase: data.phrase,
          });
        } else if (data.type === "progress") {
          setIsLoading(false);
          setProgress((prev) => [...prev, data.message || "Working…"]);
        } else if (data.type === "content" && !data.done) {
          setIsLoading(false);
          if (!assistantAdded) {
            addMessage("assistant", "");
            assistantAdded = true;
          }
          assistantMessage += data.content;
          setMessages((prev) => {
            const next = [...prev];
            const last = next.length - 1;
            if (last >= 0 && next[last].role === "assistant") {
              next[last] = { ...next[last], content: assistantMessage };
            }
            return next;
          });
        } else if (data.type === "state") {
          setProgress([]);
          setCurrentStep(data.current_step || "agent");
          if (data.structured_response) {
            setStructuredResponse(data.structured_response);
          }
          if (data.requires_input && data.tool_requests?.length) {
            // Reset the approval editor for the new tool request.
            setAgentEditing(false);
            setAgentRejecting(false);
            setAgentResponding(false);
            setAgentFeedback("");
            setAgentResponse("");
            const nextArgs = data.tool_requests[0]?.args ?? {};
            setAgentArgsText(JSON.stringify(nextArgs, null, 2));
            // Structured per-field editing (generative form) for flat args.
            setAgentArgs(
              Object.fromEntries(
                Object.entries(nextArgs).map(([k, v]) => [
                  k,
                  typeof v === "object" ? JSON.stringify(v) : String(v),
                ])
              )
            );
            setInterruptData({
              type: "agent_tool_approval",
              message: "The agent wants to run a tool",
              question: "Approve, edit, or reject the tool call",
              options: [],
              agent: {
                toolRequests: data.tool_requests,
                allowed: data.allowed || ["approve", "reject"],
              },
            });
          } else if (data.final_response && !assistantAdded) {
            addMessage("assistant", data.final_response);
          }
        }
      });
    } catch (error) {
      console.error("Agent error:", error);
      addMessage("system", "Sorry, the agent hit an error. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  // The agent + deep-agent engines share one SSE handler; only the path differs.
  const agentBase = () => (engine === "deep" ? "/deep" : "/agent");

  const startAgent = async (message: string, threadOverride?: string) => {
    await consumeAgentStream(`${agentBase()}/start`, {
      message,
      user_id: userId,
      thread_id: threadOverride,
    });
  };

  const agentDecide = async (decisions: Record<string, unknown>[]) => {
    if (!threadId) return;
    await consumeAgentStream(`${agentBase()}/decide`, {
      thread_id: threadId,
      decisions,
    });
  };

  // Switch engines: reset the conversation so each engine starts clean.
  const switchEngine = (next: "workflow" | "agent" | "deep") => {
    if (next === engine) return;
    setEngine(next);
    setThreadId(null);
    setMessages([]);
    setInterruptData(null);
    setProgress([]);
    setChatState(null);
    setCurrentStep("idle");
    setForkCheckpoint(null);
    setShowHistory(false);
    setGuardrailNotice(null);
    setStructuredResponse(null);
  };

  const continueChat = async (message: string) => {
    if (!threadId) return;

    setIsLoading(true);

    try {
      const response = await fetch(`${API_URL}/continue`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          thread_id: threadId,
          message: message,
          user_id: userId,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setChatState(data.state);
      setCurrentStep(data.state.current_step);

      if (data.requires_input && data.interrupt_message) {
        setInterruptData({
          type: "user_input",
          message: data.interrupt_message,
          question: data.interrupt_message,
          options: optionsForInterrupt(data.interrupt_message),
        });
      } else if (data.state.final_response) {
        addMessage("assistant", data.state.final_response);
        setInterruptData(null);
      }
    } catch (error) {
      console.error("Error continuing chat:", error);
      addMessage(
        "system",
        "Sorry, there was an error processing your follow-up question. Please try again."
      );
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    const isAgentic = engine === "agent" || engine === "deep";

    // Agent / Deep Agent: a tool approval is handled with buttons, not free text.
    if (isAgentic && interruptData?.agent) {
      return;
    }

    if (isAgentic) {
      addMessage("user", input);
      startAgent(input, threadId || undefined); // new thread, or follow-up turn
      setInput("");
      return;
    }

    // Workflow engine
    if (!threadId) {
      startChat(input);
    } else if (interruptData) {
      addMessage("user", input);
      const fork = forkCheckpoint || undefined;
      setForkCheckpoint(null);
      runResume(input, fork);
    } else {
      addMessage("user", input);
      continueChat(input);
    }

    setInput("");
  };

  const handleOptionClick = (option: string) => {
    // Determine the choice type based on current interrupt data
    let choiceType = "general";
    if (interruptData?.message) {
      if (interruptData.message.includes("Research Direction")) {
        choiceType = "research_direction";
      } else if (interruptData.message.includes("Choose Response Format")) {
        choiceType = "response_format";
      } else if (interruptData.message.includes("research plan")) {
        choiceType = "research_plan";
      }
    }

    addChoiceMessage(option, choiceType);

    // A single streaming resume handles every step (progress + tokens). If we
    // rewound via the history panel, fork from that checkpoint instead.
    const fork = forkCheckpoint || undefined;
    setForkCheckpoint(null);
    runResume(option, fork);

    setInterruptData(null);
  };

  // Agent engine: approve / edit / reject a pending tool call.
  // State lives in the parent so it survives re-renders during streaming.
  const renderAgentApproval = () => {
    const req = interruptData?.agent?.toolRequests?.[0];
    const allowed: string[] = interruptData?.agent?.allowed || [];
    if (!req) return null;

    const argEntries = Object.entries(req.args ?? {});
    // Per-field editing works when every arg is a primitive ("flat").
    const flat = argEntries.every(([, v]) => typeof v !== "object" || v === null);
    const coerce = (s: string): any => {
      try {
        return JSON.parse(s);
      } catch {
        return s;
      }
    };

    const submitEdit = () => {
      let parsed: any;
      if (flat) {
        parsed = Object.fromEntries(
          Object.entries(agentArgs).map(([k, v]) => [k, coerce(v)])
        );
      } else {
        try {
          parsed = JSON.parse(agentArgsText);
        } catch {
          parsed = req.args;
        }
      }
      addMessage("choice", `Edited & approved ${req.name}`, "agent");
      agentDecide([
        { type: "edit", edited_action: { name: req.name, args: parsed } },
      ]);
    };

    const mode = agentEditing
      ? "edit"
      : agentRejecting
      ? "reject"
      : agentResponding
      ? "respond"
      : "view";

    return (
      <div className="interrupt-card animate-slide-up border-purple-200 from-purple-50 to-indigo-50">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-gradient-to-br from-purple-500 to-indigo-600 rounded-lg flex items-center justify-center">
              <Settings className="w-4 h-4 text-white" />
            </div>
            <h3 className="font-semibold text-purple-900 text-sm">
              Human approval required
            </h3>
          </div>
          <code className="text-[11px] font-semibold bg-purple-100 text-purple-800 rounded-full px-2 py-0.5">
            {req.name}()
          </code>
        </div>

        {/* Structured argument view / editor (generated from the tool call) */}
        <div className="rounded-lg border border-purple-100 bg-white/70 divide-y divide-purple-50 mb-3 overflow-hidden">
          {argEntries.length === 0 && (
            <div className="px-3 py-2 text-xs text-gray-400">(no arguments)</div>
          )}
          {flat
            ? argEntries.map(([key]) => (
                <div
                  key={key}
                  className="grid grid-cols-3 gap-2 items-center px-3 py-2"
                >
                  <span className="text-xs font-medium text-gray-500 truncate">
                    {key}
                  </span>
                  {mode === "edit" ? (
                    <input
                      value={agentArgs[key] ?? ""}
                      onChange={(e) =>
                        setAgentArgs((p) => ({ ...p, [key]: e.target.value }))
                      }
                      className="col-span-2 text-xs font-mono rounded-md border border-purple-200 px-2 py-1 focus:outline-none focus:ring-2 focus:ring-purple-300"
                    />
                  ) : (
                    <span className="col-span-2 text-xs font-mono text-gray-800 break-words">
                      {agentArgs[key]}
                    </span>
                  )}
                </div>
              ))
            : mode === "edit" && (
                <textarea
                  value={agentArgsText}
                  onChange={(e) => setAgentArgsText(e.target.value)}
                  rows={4}
                  className="w-full font-mono text-xs px-3 py-2 focus:outline-none"
                />
              )}
          {!flat && mode !== "edit" && (
            <pre className="text-xs text-gray-700 overflow-x-auto px-3 py-2">
              {JSON.stringify(req.args, null, 2)}
            </pre>
          )}
        </div>

        {mode === "reject" && (
          <textarea
            value={agentFeedback}
            onChange={(e) => setAgentFeedback(e.target.value)}
            rows={2}
            placeholder="Why are you rejecting? (sent back to the agent)"
            className="w-full text-xs rounded-lg border border-rose-200 px-3 py-2 mb-2 focus:outline-none focus:ring-2 focus:ring-rose-300"
          />
        )}

        {mode === "respond" && (
          <textarea
            value={agentResponse}
            onChange={(e) => setAgentResponse(e.target.value)}
            rows={2}
            placeholder="Answer on the tool's behalf — the agent uses this instead of running it"
            className="w-full text-xs rounded-lg border border-sky-200 px-3 py-2 mb-2 focus:outline-none focus:ring-2 focus:ring-sky-300"
          />
        )}

        <div className="flex flex-wrap gap-2">
          {mode === "edit" && (
            <>
              <button
                onClick={submitEdit}
                className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg px-3 py-1.5 text-sm font-medium"
              >
                Run with edits
              </button>
              <button
                onClick={() => setAgentEditing(false)}
                className="text-sm text-gray-500 hover:text-gray-800 px-2"
              >
                Cancel
              </button>
            </>
          )}
          {mode === "reject" && (
            <>
              <button
                onClick={() => {
                  addMessage("choice", `Rejected ${req.name}`, "agent");
                  agentDecide([{ type: "reject", message: agentFeedback }]);
                }}
                className="bg-rose-600 hover:bg-rose-700 text-white rounded-lg px-3 py-1.5 text-sm font-medium"
              >
                Reject tool call
              </button>
              <button
                onClick={() => setAgentRejecting(false)}
                className="text-sm text-gray-500 hover:text-gray-800 px-2"
              >
                Cancel
              </button>
            </>
          )}
          {mode === "respond" && (
            <>
              <button
                onClick={() => {
                  addMessage("choice", `Answered ${req.name} directly`, "agent");
                  agentDecide([{ type: "respond", message: agentResponse }]);
                }}
                className="bg-sky-600 hover:bg-sky-700 text-white rounded-lg px-3 py-1.5 text-sm font-medium"
              >
                Send answer
              </button>
              <button
                onClick={() => setAgentResponding(false)}
                className="text-sm text-gray-500 hover:text-gray-800 px-2"
              >
                Cancel
              </button>
            </>
          )}
          {mode === "view" && (
            <>
              {allowed.includes("approve") && (
                <button
                  onClick={() => {
                    addMessage("choice", `Approved ${req.name}`, "agent");
                    agentDecide([{ type: "approve" }]);
                  }}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg px-4 py-1.5 text-sm font-medium"
                >
                  ✓ Approve
                </button>
              )}
              {allowed.includes("edit") && (
                <button
                  onClick={() => setAgentEditing(true)}
                  className="bg-white border border-purple-200 hover:bg-purple-50 text-purple-800 rounded-lg px-4 py-1.5 text-sm font-medium"
                >
                  ✎ Edit
                </button>
              )}
              {allowed.includes("respond") && (
                <button
                  onClick={() => setAgentResponding(true)}
                  className="bg-white border border-sky-200 hover:bg-sky-50 text-sky-700 rounded-lg px-4 py-1.5 text-sm font-medium"
                >
                  ↩ Answer
                </button>
              )}
              {allowed.includes("reject") && (
                <button
                  onClick={() => setAgentRejecting(true)}
                  className="bg-white border border-rose-200 hover:bg-rose-50 text-rose-700 rounded-lg px-4 py-1.5 text-sm font-medium"
                >
                  ✕ Reject
                </button>
              )}
            </>
          )}
        </div>
      </div>
    );
  };

  const renderInterruptOptions = () => {
    if (!interruptData?.options) return null;

    if (Array.isArray(interruptData.options)) {
      return (
        <div className="space-y-2">
          {interruptData.options.map((option, index) => {
            // Create more descriptive labels for options
            const getOptionLabel = (opt: string) => {
              const labels: { [key: string]: string } = {
                // Research planning options
                proceed: "📋 Proceed - Full comprehensive research",
                simplified: "⚡ Simplified - Quick overview with key points",
                focused: "🎯 Focused - Targeted research on specific aspects",
                cancel: "❌ Cancel - Stop the research process",
                // Research direction options
                technical: "⚙️ Technical - Deep dive into technical details",
                practical:
                  "🛠️ Practical - Real-world applications and use cases",
                recent: "📈 Recent - Latest developments and trends",
                comparative: "⚖️ Comparative - Compare different approaches",
                continue: "➡️ Continue - General comprehensive analysis",
                continue_context:
                  "🔗 Continue with Context - Build on previous conversation",
                // Response format options
                comprehensive:
                  "📚 Comprehensive - Detailed analysis with examples and explanations",
                executive:
                  "👔 Executive - Concise summary with key insights and recommendations",
                structured:
                  "📊 Structured - Clear headings, sections, and bullet points",
                conversational:
                  "💬 Conversational - Natural, friendly tone with explanations",
                bullet_points:
                  "📝 Bullet Points - Quick reference format with organized lists",
              };
              return labels[opt] || opt;
            };

            return (
              <button
                key={index}
                onClick={() => handleOptionClick(option)}
                className="option-button w-full group text-left"
                disabled={isLoading}
              >
                <div className="flex items-center space-x-2">
                  <div className="w-2 h-2 bg-blue-400 rounded-full group-hover:bg-blue-600 transition-colors flex-shrink-0"></div>
                  <span className="font-medium text-blue-900 text-sm leading-relaxed">
                    {getOptionLabel(option)}
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      );
    }

    return (
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {Object.entries(interruptData.options).map(([key, value]) => (
          <button
            key={key}
            onClick={() => handleOptionClick(key)}
            className="option-button group"
            disabled={isLoading}
          >
            <div className="flex items-center justify-between">
              <div className="font-semibold text-blue-900 mb-1 text-sm">
                {value}
              </div>
              <div className="w-5 h-5 border-2 border-blue-300 rounded-full group-hover:border-blue-500 group-hover:bg-blue-500 transition-all duration-200 flex items-center justify-center">
                <CheckCircle className="w-3 h-3 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            </div>
          </button>
        ))}
      </div>
    );
  };

  return (
    <div className="flex flex-col h-screen bg-mesh">
      {/* Header */}
      <div className="bg-white/90 backdrop-blur-lg shadow-soft border-b border-white/20 px-4 py-3">
        <div className="flex items-center space-x-3">
          <div className="relative">
            <div className="w-9 h-9 bg-gradient-to-br from-primary-500 to-secondary-600 rounded-xl flex items-center justify-center shadow-soft-lg">
              <Brain className="w-5 h-5 text-white" />
            </div>
            <div className="absolute -top-0.5 -right-0.5 w-3 h-3 bg-green-400 rounded-full border border-white animate-pulse-soft"></div>
          </div>
          <div>
            <h1 className="text-lg font-bold text-gradient">
              AI Research Assistant
            </h1>
            <p className="text-gray-600 text-xs font-medium">
              Intelligent research with interactive guidance
            </p>
          </div>
          <div className="ml-auto flex items-center space-x-3">
            {/* Engine toggle: deterministic workflow vs. agentic loop */}
            <div className="flex items-center bg-gray-100 rounded-full p-0.5 border border-gray-200">
              <button
                onClick={() => switchEngine("workflow")}
                className={`text-xs font-medium px-3 py-1 rounded-full transition-colors ${
                  engine === "workflow"
                    ? "bg-white text-indigo-700 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                }`}
                title="Deterministic StateGraph with fixed interrupts + parallel Send"
              >
                Workflow
              </button>
              <button
                onClick={() => switchEngine("agent")}
                className={`text-xs font-medium px-3 py-1 rounded-full transition-colors ${
                  engine === "agent"
                    ? "bg-white text-purple-700 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                }`}
                title="Model-driven create_agent + human-in-the-loop tool approval"
              >
                Agent
              </button>
              <button
                onClick={() => switchEngine("deep")}
                className={`text-xs font-medium px-3 py-1 rounded-full transition-colors ${
                  engine === "deep"
                    ? "bg-white text-teal-700 shadow-sm"
                    : "text-gray-500 hover:text-gray-700"
                }`}
                title="Deep Agent: plans, spawns researcher/critic subagents, and pauses for tool approval"
              >
                Deep Agent
              </button>
            </div>
            {threadId && (
              <div className="hidden sm:flex items-center space-x-2 bg-green-50 px-3 py-1.5 rounded-full border border-green-200">
                <div className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse"></div>
                <span className="text-xs font-medium text-green-700">
                  Active Session
                </span>
              </div>
            )}
            {threadId && engine === "workflow" && (
              <button
                onClick={loadHistory}
                title="Rewind to an earlier step (time travel)"
                className="flex items-center gap-1 text-xs font-medium text-amber-700 hover:text-amber-900 bg-amber-50 hover:bg-amber-100 border border-amber-200 rounded-full px-3 py-1.5 transition-colors"
              >
                <History className="w-3.5 h-3.5" /> History
              </button>
            )}
            <Link
              href="/approval"
              className="text-xs font-medium text-indigo-600 hover:text-indigo-800 bg-indigo-50 hover:bg-indigo-100 border border-indigo-100 rounded-full px-3 py-1.5 transition-colors"
            >
              Approval workflow →
            </Link>
          </div>
        </div>
      </div>

      {/* Status strip: which optional backend features are active */}
      {capabilities && (
        <div className="bg-white/60 backdrop-blur-sm border-b border-white/30 px-4 py-1.5">
          <div className="flex flex-wrap items-center gap-2 text-[11px]">
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 border font-medium ${
                capabilities.model?.mock
                  ? "bg-gray-50 border-gray-200 text-gray-500"
                  : "bg-purple-50 border-purple-200 text-purple-700"
              }`}
              title={
                capabilities.model?.mock
                  ? "Offline mock model — set LLM_MODEL + a provider key for a real LLM"
                  : "Live provider model"
              }
            >
              <Bot className="w-3 h-3" />
              {capabilities.model?.mock ? "Mock model" : capabilities.model?.name}
            </span>

            {capabilities.guardrails?.enabled && (
              <span
                className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 border font-medium bg-emerald-50 border-emerald-200 text-emerald-700"
                title={
                  "Guardrail middleware active" +
                  (capabilities.guardrails.redact_pii ? " · redacts PII" : "") +
                  (capabilities.guardrails.blocklist_count
                    ? ` · ${capabilities.guardrails.blocklist_count} blocked phrase(s)`
                    : "")
                }
              >
                <ShieldCheck className="w-3 h-3" />
                Guardrails
              </span>
            )}

            {capabilities.semantic_memory && (
              <span
                className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 border font-medium bg-blue-50 border-blue-200 text-blue-700"
                title="Long-term memory uses embeddings for semantic recall"
              >
                <Brain className="w-3 h-3" />
                Semantic memory
              </span>
            )}

            {capabilities.structured_output && (
              <span
                className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 border font-medium bg-indigo-50 border-indigo-200 text-indigo-700"
                title="The agent returns a validated ResearchSummary object"
              >
                <ListChecks className="w-3 h-3" />
                Structured output
              </span>
            )}

            {capabilities.mcp?.enabled ? (
              <span
                className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 border font-medium bg-teal-50 border-teal-200 text-teal-700"
                title={`MCP tools: ${capabilities.mcp.tools.join(", ")}`}
              >
                <Settings className="w-3 h-3" />
                {capabilities.mcp.tools.length} MCP tool
                {capabilities.mcp.tools.length === 1 ? "" : "s"}
                {capabilities.mcp.tools.length > 0 && (
                  <span className="text-teal-500 font-normal">
                    · {capabilities.mcp.tools.slice(0, 3).join(", ")}
                    {capabilities.mcp.tools.length > 3 ? "…" : ""}
                  </span>
                )}
              </span>
            ) : (
              <span
                className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 border font-medium bg-gray-50 border-gray-200 text-gray-400"
                title="Set MCP_SERVERS to load tools from Model Context Protocol servers"
              >
                <Settings className="w-3 h-3" />
                No MCP tools
              </span>
            )}

            {Array.isArray(capabilities.middleware) &&
              capabilities.middleware.length > 0 && (
                <span
                  className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 border font-medium bg-violet-50 border-violet-200 text-violet-700"
                  title={`Agent middleware: ${capabilities.middleware.join(" · ")}`}
                >
                  <Layers className="w-3 h-3" />
                  {capabilities.middleware.length} middleware
                </span>
              )}

            {capabilities.resilience && (
              <span
                className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 border font-medium bg-amber-50 border-amber-200 text-amber-700"
                title={
                  `Resilient workflow — retries ×${capabilities.resilience.retry_max_attempts}` +
                  (capabilities.resilience.node_timeout_seconds
                    ? ` · ${capabilities.resilience.node_timeout_seconds}s node timeout`
                    : "") +
                  (capabilities.resilience.compensation
                    ? " · graceful fallback on failure"
                    : "")
                }
              >
                <ShieldCheck className="w-3 h-3" />
                Resilient
              </span>
            )}

            {capabilities.deep_agent?.installed && (
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 border font-medium ${
                  capabilities.deep_agent.available
                    ? "bg-teal-50 border-teal-200 text-teal-700"
                    : "bg-gray-50 border-gray-200 text-gray-400"
                }`}
                title={
                  capabilities.deep_agent.available
                    ? "Deep Agent engine ready — plans & delegates to subagents"
                    : capabilities.deep_agent.reason
                }
              >
                <Brain className="w-3 h-3" />
                Deep Agent{capabilities.deep_agent.available ? "" : " (needs model)"}
              </span>
            )}

            {capabilities.agui?.enabled && (
              <span
                className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 border font-medium bg-fuchsia-50 border-fuchsia-200 text-fuchsia-700"
                title={`AG-UI protocol endpoint at ${capabilities.agui.path} — connect any AG-UI client (e.g. CopilotKit)`}
              >
                <Layers className="w-3 h-3" />
                AG-UI
              </span>
            )}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center py-12 animate-fade-in">
            <div className="relative mb-6">
              <div className="w-16 h-16 bg-gradient-to-br from-primary-500 to-secondary-600 rounded-2xl flex items-center justify-center mx-auto shadow-soft-lg">
                <Brain className="w-8 h-8 text-white" />
              </div>
              <div className="absolute -top-1 -right-1 w-4 h-4 bg-yellow-400 rounded-full flex items-center justify-center animate-bounce-soft">
                <span className="text-xs">✨</span>
              </div>
            </div>
            <h2 className="text-xl font-bold text-gray-900 mb-3">
              Welcome to AI Research Assistant
            </h2>
            <p className="text-gray-600 max-w-xl mx-auto text-sm leading-relaxed">
              {engine === "deep"
                ? "Deep Agent engine: it plans with a to-do list, delegates to researcher & critic subagents, and pauses for tool approval. Its planning shines with a real model."
                : engine === "agent"
                ? "Agent engine: a model-driven create_agent loop. It decides when to search and pauses for your approval before running a tool (approve / edit / reject)."
                : "Workflow engine: a deterministic graph with fixed interrupt points and parallel Send research. Switch to Agent or Deep Agent in the header to compare paradigms."}
            </p>
            {engine === "deep" && capabilities?.deep_agent?.available === false && (
              <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-3 py-1.5">
                <AlertCircle className="w-3.5 h-3.5 shrink-0" />
                {capabilities.deep_agent.reason}
              </p>
            )}
            <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-3 max-w-3xl mx-auto">
              <div className="p-4 bg-white/60 backdrop-blur-sm rounded-xl border border-white/40 shadow-soft">
                <Search className="w-6 h-6 text-primary-600 mx-auto mb-2" />
                <h3 className="font-semibold text-gray-900 mb-1 text-sm">
                  Deep Research
                </h3>
                <p className="text-xs text-gray-600">
                  Comprehensive information gathering from multiple sources
                </p>
              </div>
              <div className="p-4 bg-white/60 backdrop-blur-sm rounded-xl border border-white/40 shadow-soft">
                <Brain className="w-6 h-6 text-primary-600 mx-auto mb-2" />
                <h3 className="font-semibold text-gray-900 mb-1 text-sm">
                  Smart Analysis
                </h3>
                <p className="text-xs text-gray-600">
                  AI-powered synthesis and insight generation
                </p>
              </div>
              <div className="p-4 bg-white/60 backdrop-blur-sm rounded-xl border border-white/40 shadow-soft">
                <MessageSquare className="w-6 h-6 text-primary-600 mx-auto mb-2" />
                <h3 className="font-semibold text-gray-900 mb-1 text-sm">
                  Interactive Guidance
                </h3>
                <p className="text-xs text-gray-600">
                  Real-time decisions and personalized responses
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Message Rendering with Choice Message Support */}
        {messages.map((message, index) => (
          <div key={index} className="animate-fade-in">
            {message.role === "choice" ? (
              // Compact choice indicator positioned above assistant message
              <div className="flex justify-start mb-1">
                <div className="choice-compact">
                  <div className="w-3 h-3 bg-gradient-to-br from-purple-500 to-indigo-600 rounded-full flex items-center justify-center">
                    <CheckCircle className="w-2 h-2 text-white" />
                  </div>
                  <span className="choice-badge">
                    {message.choiceType === "research_plan"
                      ? "Plan"
                      : message.choiceType === "research_direction"
                      ? "Direction"
                      : message.choiceType === "response_format"
                      ? "Format"
                      : "Choice"}
                  </span>
                  <span className="text-purple-800 font-medium text-xs">
                    {message.content}
                  </span>
                </div>
              </div>
            ) : (
              // Regular message rendering
              <div
                className={`flex ${
                  message.role === "user" ? "justify-end" : "justify-start"
                } mb-4`}
              >
                <div
                  className={`flex items-start space-x-3 max-w-4xl ${
                    message.role === "user"
                      ? "flex-row-reverse space-x-reverse"
                      : ""
                  }`}
                >
                  <div
                    className={`
                      avatar-sm
                      ${
                        message.role === "user"
                          ? "bg-gradient-to-br from-primary-500 to-primary-600"
                          : message.role === "system"
                          ? "bg-gradient-to-br from-orange-400 to-yellow-500"
                          : "bg-gradient-to-br from-gray-700 to-gray-800"
                      }
                    `}
                  >
                    {message.role === "user" ? (
                      <User className="w-4 h-4 text-white" />
                    ) : message.role === "system" ? (
                      <AlertCircle className="w-4 h-4 text-white" />
                    ) : (
                      <Bot className="w-4 h-4 text-white" />
                    )}
                  </div>

                  <div
                    className={`
                      message-bubble
                      ${
                        message.role === "user"
                          ? "user-message"
                          : message.role === "system"
                          ? "system-message"
                          : "assistant-message"
                      }
                    `}
                  >
                    {message.role === "assistant" ? (
                      <div className="prose prose-gray prose-sm max-w-none leading-relaxed">
                        <ReactMarkdown
                          components={{
                            p: ({ children }) => (
                              <p className="mb-3 last:mb-0 leading-relaxed text-sm">
                                {children}
                              </p>
                            ),
                            strong: ({ children }) => (
                              <strong className="font-semibold text-gray-900">
                                {children}
                              </strong>
                            ),
                            em: ({ children }) => (
                              <em className="italic text-gray-700">
                                {children}
                              </em>
                            ),
                            code: ({ children }) => (
                              <code className="bg-gray-100 text-gray-900 px-1.5 py-0.5 rounded text-xs font-mono">
                                {children}
                              </code>
                            ),
                            pre: ({ children }) => (
                              <pre className="bg-gray-100 p-3 rounded-lg overflow-x-auto mb-3 text-xs">
                                {children}
                              </pre>
                            ),
                            h1: ({ children }) => (
                              <h1 className="text-lg font-bold text-gray-900 mb-3 mt-4 first:mt-0">
                                {children}
                              </h1>
                            ),
                            h2: ({ children }) => (
                              <h2 className="text-base font-bold text-gray-900 mb-2 mt-4 first:mt-0">
                                {children}
                              </h2>
                            ),
                            h3: ({ children }) => (
                              <h3 className="text-sm font-bold text-gray-900 mb-2 mt-3 first:mt-0">
                                {children}
                              </h3>
                            ),
                            h4: ({ children }) => (
                              <h4 className="text-sm font-semibold text-gray-900 mb-1 mt-3 first:mt-0">
                                {children}
                              </h4>
                            ),
                            ul: ({ children }) => (
                              <ul className="list-disc list-inside mb-3 space-y-1 pl-3 text-sm">
                                {children}
                              </ul>
                            ),
                            ol: ({ children }) => (
                              <ol className="list-decimal list-inside mb-3 space-y-1 pl-3 text-sm">
                                {children}
                              </ol>
                            ),
                            li: ({ children }) => (
                              <li className="text-gray-800 leading-relaxed text-sm">
                                {children}
                              </li>
                            ),
                            blockquote: ({ children }) => (
                              <blockquote className="border-l-3 border-gray-300 pl-3 italic text-gray-700 mb-3 text-sm">
                                {children}
                              </blockquote>
                            ),
                            a: ({ children, href }) => (
                              <a
                                href={href}
                                className="text-blue-600 hover:text-blue-800 underline text-sm"
                                target="_blank"
                                rel="noopener noreferrer"
                              >
                                {children}
                              </a>
                            ),
                            table: ({ children }) => (
                              <div className="overflow-x-auto mb-3">
                                <table className="min-w-full border border-gray-300 rounded-lg text-xs">
                                  {children}
                                </table>
                              </div>
                            ),
                            thead: ({ children }) => (
                              <thead className="bg-gray-50">{children}</thead>
                            ),
                            th: ({ children }) => (
                              <th className="border border-gray-300 px-3 py-2 text-left font-semibold text-xs">
                                {children}
                              </th>
                            ),
                            td: ({ children }) => (
                              <td className="border border-gray-300 px-3 py-2 text-xs">
                                {children}
                              </td>
                            ),
                          }}
                        >
                          {message.content}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <div className="whitespace-pre-wrap leading-relaxed text-sm">
                        {message.content}
                      </div>
                    )}
                    <div
                      className={`text-xs mt-2 flex items-center space-x-2 ${
                        message.role === "user"
                          ? "text-primary-100"
                          : "text-gray-500"
                      }`}
                    >
                      <span>{message.timestamp.toLocaleTimeString()}</span>
                      {message.role === "assistant" && (
                        <span className="flex items-center space-x-1">
                          <CheckCircle className="w-3 h-3" />
                          <span>Verified</span>
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}

        {/* Interrupt Options */}
        {interruptData && !interruptData.agent && (
          <div className="interrupt-card animate-slide-up">
            <div className="flex items-center space-x-2 mb-3">
              <div className="w-6 h-6 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center">
                <AlertCircle className="w-4 h-4 text-white" />
              </div>
              <h3 className="font-semibold text-blue-900 text-sm">
                Research Assistant
              </h3>
            </div>
            <div className="text-blue-800 mb-4 text-sm leading-relaxed">
              <div className="prose prose-blue prose-sm max-w-none">
                <ReactMarkdown
                  components={{
                    p: ({ children }) => (
                      <p className="mb-3 last:mb-0 text-sm">{children}</p>
                    ),
                    strong: ({ children }) => (
                      <strong className="font-semibold text-blue-900">
                        {children}
                      </strong>
                    ),
                    em: ({ children }) => (
                      <em className="italic text-blue-700">{children}</em>
                    ),
                    code: ({ children }) => (
                      <code className="bg-blue-100 text-blue-900 px-1.5 py-0.5 rounded text-xs font-mono">
                        {children}
                      </code>
                    ),
                    h1: ({ children }) => (
                      <h1 className="text-base font-semibold text-blue-900 mb-2">
                        {children}
                      </h1>
                    ),
                    h2: ({ children }) => (
                      <h2 className="text-sm font-semibold text-blue-900 mb-2">
                        {children}
                      </h2>
                    ),
                    h3: ({ children }) => (
                      <h3 className="text-sm font-semibold text-blue-900 mb-1">
                        {children}
                      </h3>
                    ),
                    ul: ({ children }) => (
                      <ul className="list-disc list-inside mb-3 space-y-1 text-sm">
                        {children}
                      </ul>
                    ),
                    ol: ({ children }) => (
                      <ol className="list-decimal list-inside mb-3 space-y-1 text-sm">
                        {children}
                      </ol>
                    ),
                    li: ({ children }) => (
                      <li className="text-blue-800 text-sm">{children}</li>
                    ),
                  }}
                >
                  {interruptData.question}
                </ReactMarkdown>
              </div>
            </div>
            {renderInterruptOptions()}
          </div>
        )}

        {/* Agent engine: tool-approval interrupt */}
        {interruptData?.agent && renderAgentApproval()}

        {/* Feature A: live parallel-research progress (Send fan-out) */}
        {progress.length > 0 && (
          <div className="flex justify-start animate-fade-in">
            <div className="bg-white/80 backdrop-blur-sm border border-blue-100 rounded-xl px-4 py-3 shadow-soft max-w-2xl w-full">
              <div className="flex items-center gap-2 text-sm font-semibold text-blue-800 mb-2">
                <Search className="w-4 h-4 animate-pulse" /> Researching in parallel
              </div>
              <ul className="space-y-1">
                {progress.map((p, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-xs text-gray-600 animate-slide-up"
                  >
                    <CheckCircle className="w-3.5 h-3.5 text-green-500 mt-0.5 shrink-0" />
                    <span>{p}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        )}

        {/* Guardrail signal: PII redaction / blocklist (agent engine) */}
        {guardrailNotice && (
          <div className="flex justify-start animate-fade-in">
            {guardrailNotice.action === "blocked" ? (
              <div className="flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 rounded-full px-3 py-1.5 text-xs font-medium shadow-soft">
                <ShieldAlert className="w-3.5 h-3.5 shrink-0" />
                <span>
                  Guardrail blocked this request
                  {guardrailNotice.phrase ? ` (“${guardrailNotice.phrase}”)` : ""}
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-2 bg-emerald-50 border border-emerald-200 text-emerald-700 rounded-full px-3 py-1.5 text-xs font-medium shadow-soft">
                <ShieldCheck className="w-3.5 h-3.5 shrink-0" />
                <span>
                  Guardrail redacted {guardrailNotice.count ?? "some"} PII item
                  {guardrailNotice.count === 1 ? "" : "s"} before the model
                </span>
              </div>
            )}
          </div>
        )}

        {/* Structured output: ResearchSummary (AGENT_STRUCTURED_OUTPUT) */}
        {structuredResponse && (
          <div className="flex justify-start animate-fade-in">
            <div className="bg-white border border-indigo-100 rounded-xl px-4 py-3 shadow-soft max-w-2xl w-full">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 text-sm font-semibold text-indigo-800">
                  <ListChecks className="w-4 h-4" /> Structured summary
                </div>
                {structuredResponse.confidence && (
                  <span className="text-[11px] font-medium text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-full px-2 py-0.5">
                    confidence: {structuredResponse.confidence}
                  </span>
                )}
              </div>
              {structuredResponse.summary && (
                <p className="text-sm text-gray-700 mb-2">
                  {structuredResponse.summary}
                </p>
              )}
              {Array.isArray(structuredResponse.key_findings) &&
                structuredResponse.key_findings.length > 0 && (
                  <ul className="space-y-1 mb-2">
                    {structuredResponse.key_findings.map((f: string, i: number) => (
                      <li
                        key={i}
                        className="flex items-start gap-2 text-xs text-gray-600"
                      >
                        <CheckCircle className="w-3.5 h-3.5 text-indigo-500 mt-0.5 shrink-0" />
                        <span>{f}</span>
                      </li>
                    ))}
                  </ul>
                )}
              {Array.isArray(structuredResponse.sources) &&
                structuredResponse.sources.length > 0 && (
                  <div className="text-[11px] text-gray-400 border-t border-gray-100 pt-2">
                    Sources: {structuredResponse.sources.join(" · ")}
                  </div>
                )}
            </div>
          </div>
        )}

        {/* Feature C: time-travel / checkpoint history panel */}
        {showHistory && (
          <div className="flex justify-start animate-fade-in">
            <div className="bg-white border border-amber-200 rounded-xl px-4 py-3 shadow-soft max-w-2xl w-full">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2 text-sm font-semibold text-amber-800">
                  <History className="w-4 h-4" /> Rewind to an earlier step
                </div>
                <button
                  onClick={() => setShowHistory(false)}
                  className="text-xs text-gray-400 hover:text-gray-700"
                >
                  Close
                </button>
              </div>
              <p className="text-xs text-gray-500 mb-3">
                Jump back to a previous interrupt and pick a different path — the
                original run is preserved (LangGraph time travel).
              </p>
              <div className="space-y-1.5 max-h-60 overflow-y-auto">
                {history.filter((c) => c.has_interrupt).length === 0 && (
                  <p className="text-xs text-gray-400">
                    No earlier decision points yet.
                  </p>
                )}
                {history
                  .filter((c) => c.has_interrupt)
                  .map((c) => (
                    <button
                      key={c.checkpoint_id}
                      onClick={() => rewindTo(c)}
                      className="w-full flex items-center justify-between gap-2 text-left bg-amber-50 hover:bg-amber-100 border border-amber-100 rounded-lg px-3 py-2 transition-colors"
                    >
                      <span className="flex items-center gap-2 text-xs text-gray-700">
                        <Clock className="w-3.5 h-3.5 text-amber-600" />
                        Step {c.step}: {(c.next && c.next[0]) || c.current_step}
                      </span>
                      <span className="text-[11px] font-medium text-amber-700">
                        Rewind →
                      </span>
                    </button>
                  ))}
              </div>
            </div>
          </div>
        )}

        {/* Loading indicator */}
        {isLoading && (
          <div className="flex justify-start animate-fade-in">
            <div className="flex items-center space-x-3">
              <div className="avatar-sm bg-gradient-to-br from-gray-700 to-gray-800">
                <Bot className="w-4 h-4 text-white" />
              </div>
              <div className="bg-white/80 backdrop-blur-sm border border-white/40 rounded-xl px-4 py-3 shadow-soft">
                <div className="flex items-center space-x-2">
                  <div className="relative">
                    <Loader2 className="w-4 h-4 animate-spin text-primary-600" />
                  </div>
                  <span className="text-gray-700 font-medium text-sm">
                    {currentStep === "planning"
                      ? "Planning research strategy..."
                      : currentStep === "information_gathering"
                      ? "Gathering information..."
                      : currentStep === "analysis"
                      ? "Analyzing findings..."
                      : "Processing your request..."}
                  </span>
                </div>
                <div className="mt-2 w-full bg-gray-200 rounded-full h-1">
                  <div
                    className="bg-gradient-to-r from-primary-500 to-secondary-500 h-1 rounded-full animate-pulse"
                    style={{ width: "60%" }}
                  ></div>
                </div>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="bg-white/90 backdrop-blur-lg border-t border-white/20 px-4 py-4">
        <form
          onSubmit={handleSubmit}
          className="flex space-x-3 max-w-6xl mx-auto"
        >
          <div className="flex-1 relative">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={
                interruptData?.agent
                  ? "Approve / edit / reject the tool call above…"
                  : !threadId
                  ? engine === "deep"
                    ? "Ask a research question — the deep agent will plan & delegate…"
                    : engine === "agent"
                    ? "Ask the agent anything (it decides when to search)…"
                    : "Ask me anything to start your research..."
                  : interruptData
                  ? "Type your response or click an option above..."
                  : "Continue the conversation..."
              }
              className="input-field w-full pr-10"
              disabled={isLoading || !!interruptData?.agent}
            />
            {input && (
              <div className="absolute right-3 top-1/2 transform -translate-y-1/2">
                <div className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse"></div>
              </div>
            )}
          </div>
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="send-button flex items-center space-x-2"
          >
            <Send className="w-4 h-4" />
            <span className="hidden sm:inline font-medium">Send</span>
          </button>
        </form>

        {!threadId && (
          <div className="mt-3 text-center">
            <p className="text-xs text-gray-500">
              Start with questions like: "Explain quantum computing" or
              "Research the latest AI trends"
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
