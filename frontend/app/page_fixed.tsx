"use client";

import { useState, useEffect, useRef } from "react";
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
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

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
      const response = await fetch("http://localhost:8000/start", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setThreadId(data.thread_id);
      setChatState(data.state);
      setCurrentStep(data.state.current_step);

      if (data.requires_input && data.interrupt_message) {
        // Detect interrupt type and set appropriate options
        let options = ["proceed", "simplified", "focused", "cancel"]; // default for research planning

        if (
          data.interrupt_message.includes("Research Direction") ||
          data.interrupt_message.includes("explore any specific angle")
        ) {
          options = [
            "technical",
            "practical",
            "recent",
            "comparative",
            "continue",
          ];
        } else if (
          data.interrupt_message.includes("Choose Response Format") ||
          data.interrupt_message.includes("presentation style")
        ) {
          options = [
            "comprehensive",
            "executive",
            "structured",
            "conversational",
            "bullet_points",
          ];
        }

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

  const resumeChat = async (choice: string, userInput?: string) => {
    if (!threadId) return;

    setIsLoading(true);

    try {
      const response = await fetch("http://localhost:8000/resume", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          thread_id: threadId,
          choice,
          user_input: userInput || choice,
        }),
      });

      const data = await response.json();
      setChatState(data.state);
      setCurrentStep(data.state.current_step);

      if (data.requires_input && data.interrupt_message) {
        // Detect interrupt type and set appropriate options
        let options = ["proceed", "simplified", "focused", "cancel"]; // default for research planning

        if (
          data.interrupt_message.includes("Research Direction") ||
          data.interrupt_message.includes("explore any specific angle")
        ) {
          options = [
            "technical",
            "practical",
            "recent",
            "comparative",
            "continue",
          ];
        } else if (
          data.interrupt_message.includes("Choose Response Format") ||
          data.interrupt_message.includes("presentation style")
        ) {
          options = [
            "comprehensive",
            "executive",
            "structured",
            "conversational",
            "bullet_points",
          ];
        }

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
        setInterruptData(null);
      }
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

  const continueChat = async (message: string) => {
    if (!threadId) return;

    setIsLoading(true);

    try {
      const response = await fetch("http://localhost:8000/continue", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          thread_id: threadId,
          message: message,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      setChatState(data.state);
      setCurrentStep(data.state.current_step);

      if (data.requires_input && data.interrupt_message) {
        // Detect interrupt type and set appropriate options
        let options = ["proceed", "simplified", "focused", "cancel"]; // default for research planning

        if (
          data.interrupt_message.includes("Research Direction") ||
          data.interrupt_message.includes("explore any specific angle")
        ) {
          options = [
            "technical",
            "practical",
            "recent",
            "comparative",
            "continue",
            "continue_context",
          ];
        } else if (
          data.interrupt_message.includes("Choose Response Format") ||
          data.interrupt_message.includes("presentation style")
        ) {
          options = [
            "comprehensive",
            "executive",
            "structured",
            "conversational",
            "bullet_points",
          ];
        }

        // Create interrupt data structure
        const interruptData = {
          type: "user_input",
          message: data.interrupt_message,
          question: data.interrupt_message,
          options: options,
        };
        setInterruptData(interruptData);
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

  // Streaming function using EventSource for Server-Sent Events
  const streamResponse = async (choice: string, userInput?: string) => {
    if (!threadId) return;

    setIsLoading(true);
    setInterruptData(null);

    // Don't add user choice as a message here since we already added it as a choice message

    try {
      // Create EventSource for streaming
      const eventSource = new EventSource(
        `http://localhost:8000/stream?thread_id=${threadId}&choice=${encodeURIComponent(
          choice
        )}`
      );

      let assistantMessage = "";

      // Add initial empty assistant message that we'll update
      addMessage("assistant", "");

      // Clear loading state once streaming starts
      setIsLoading(false);

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          // Clear loading state as soon as we start receiving data
          if (data.type === "content" && !data.done) {
            setIsLoading(false);

            // Accumulate streaming content
            assistantMessage += data.content;

            // Update the last message (which should be the assistant message)
            setMessages((prev) => {
              const newMessages = [...prev];
              const lastIndex = newMessages.length - 1;
              if (
                lastIndex >= 0 &&
                newMessages[lastIndex].role === "assistant"
              ) {
                newMessages[lastIndex] = {
                  ...newMessages[lastIndex],
                  content: assistantMessage,
                };
              }
              return newMessages;
            });
          } else if (data.done) {
            // Streaming complete
            eventSource.close();
            setIsLoading(false);
          }
        } catch (error) {
          console.error("Error parsing stream data:", error);
        }
      };

      eventSource.onerror = (error) => {
        console.error("EventSource error:", error);
        eventSource.close();
        setIsLoading(false);
        addMessage(
          "system",
          "Sorry, there was an error with the streaming response."
        );
      };

      // Clean up on component unmount or when streaming completes
      return () => {
        eventSource.close();
      };
    } catch (error) {
      console.error("Error starting stream:", error);
      setIsLoading(false);
      addMessage("system", "Sorry, there was an error starting the stream.");
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    if (!threadId) {
      startChat(input);
    } else if (interruptData) {
      // If there's interrupt data, we're in the middle of a conversation flow
      addMessage("user", input);
      resumeChat(input);
    } else {
      // If there's no interrupt data but we have a threadId, this is a follow-up question
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

    // Check if this is likely the final response formatting choice
    const formatChoices = [
      "comprehensive",
      "executive",
      "structured",
      "conversational",
      "bullet_points",
    ];

    if (formatChoices.includes(option)) {
      // Add choice message instead of user message
      addChoiceMessage(option, choiceType);
      // Use streaming for the final response
      streamResponse(option);
    } else {
      // Add choice message instead of user message
      addChoiceMessage(option, choiceType);
      // Use regular resume for other interrupt choices
      resumeChat(option);
    }

    setInterruptData(null);
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
          {threadId && (
            <div className="ml-auto flex items-center space-x-2 bg-green-50 px-3 py-1.5 rounded-full border border-green-200">
              <div className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse"></div>
              <span className="text-xs font-medium text-green-700">
                Active Session
              </span>
            </div>
          )}
        </div>
      </div>

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
              Ask me anything and I'll conduct thorough research with
              interactive guidance to provide you with comprehensive,
              well-analyzed answers.
            </p>
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
              // Special rendering for choice messages
              <div className="flex justify-center mb-4">
                <div className="choice-message max-w-2xl">
                  <div className="flex items-center justify-center space-x-2 mb-2">
                    <div className="w-5 h-5 bg-gradient-to-br from-purple-500 to-indigo-600 rounded-lg flex items-center justify-center">
                      <CheckCircle className="w-3 h-3 text-white" />
                    </div>
                    <span className="choice-badge">
                      {message.choiceType === "research_plan"
                        ? "Research Plan"
                        : message.choiceType === "research_direction"
                        ? "Research Direction"
                        : message.choiceType === "response_format"
                        ? "Response Format"
                        : "Selection"}
                    </span>
                  </div>
                  <div className="text-center text-purple-800 font-medium text-sm">
                    {message.content}
                  </div>
                  <div className="text-xs text-purple-600 text-center mt-1">
                    {message.timestamp.toLocaleTimeString()}
                  </div>
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
        {interruptData && (
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
                !threadId
                  ? "Ask me anything to start your research..."
                  : interruptData
                  ? "Type your response or click an option above..."
                  : "Continue the conversation..."
              }
              className="input-field w-full pr-10"
              disabled={isLoading}
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
