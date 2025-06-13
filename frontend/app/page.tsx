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
  role: "user" | "assistant" | "system";
  content: string;
  timestamp: Date;
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
  refining_research: "Refining research direction",
  analysis: "Analyzing information",
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
    role: "user" | "assistant" | "system",
    content: string
  ) => {
    const newMessage: Message = {
      role,
      content,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, newMessage]);
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
        
        if (data.interrupt_message.includes("Research Direction") || data.interrupt_message.includes("explore any specific angle")) {
          options = ["technical", "practical", "recent", "comparative", "continue"];
        } else if (data.interrupt_message.includes("presentation style") || data.interrupt_message.includes("comprehensive") || data.interrupt_message.includes("executive")) {
          options = ["comprehensive", "executive", "structured", "conversational", "bullet_points"];
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
        
        if (data.interrupt_message.includes("Research Direction") || data.interrupt_message.includes("explore any specific angle")) {
          options = ["technical", "practical", "recent", "comparative", "continue"];
        } else if (data.interrupt_message.includes("presentation style") || data.interrupt_message.includes("comprehensive") || data.interrupt_message.includes("executive")) {
          options = ["comprehensive", "executive", "structured", "conversational", "bullet_points"];
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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim()) return;

    if (!threadId) {
      startChat(input);
    } else {
      addMessage("user", input);
      resumeChat(input);
    }

    setInput("");
  };

  const handleOptionClick = (option: string) => {
    addMessage("user", option);
    resumeChat(option);
    setInterruptData(null);
  };

  const renderInterruptOptions = () => {
    if (!interruptData?.options) return null;

    if (Array.isArray(interruptData.options)) {
      return (
        <div className="space-y-3">
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
                practical: "🛠️ Practical - Real-world applications and use cases",
                recent: "📈 Recent - Latest developments and trends",
                comparative: "⚖️ Comparative - Compare different approaches",
                continue: "➡️ Continue - General comprehensive analysis",
                // Response format options
                comprehensive: "📚 Comprehensive - Detailed analysis with examples and explanations",
                executive: "👔 Executive - Concise summary with key insights and recommendations",
                structured: "📊 Structured - Clear headings, sections, and bullet points",
                conversational: "💬 Conversational - Natural, friendly tone with explanations",
                bullet_points: "📝 Bullet Points - Quick reference format with organized lists"
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
                <div className="flex items-center space-x-3">
                  <div className="w-3 h-3 bg-blue-400 rounded-full group-hover:bg-blue-600 transition-colors flex-shrink-0"></div>
                  <span className="font-medium text-blue-900 text-base leading-relaxed">
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
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {Object.entries(interruptData.options).map(([key, value]) => (
          <button
            key={key}
            onClick={() => handleOptionClick(key)}
            className="option-button group"
            disabled={isLoading}
          >
            <div className="flex items-center justify-between">
              <div className="font-bold text-blue-900 mb-2">{value}</div>
              <div className="w-6 h-6 border-2 border-blue-300 rounded-full group-hover:border-blue-500 group-hover:bg-blue-500 transition-all duration-200 flex items-center justify-center">
                <CheckCircle className="w-4 h-4 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
              </div>
            </div>
          </button>
        ))}
      </div>
    );
  };

  const renderProgressBar = () => {
    const steps = [
      "planning",
      "information_gathering",
      "analysis",
      "response_formatting",
      "completed",
    ];
    const currentIndex = steps.indexOf(currentStep);

    return (
      <div className="bg-white/80 backdrop-blur-sm rounded-2xl shadow-soft border border-white/40 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-bold text-gray-800">Research Progress</h3>
          <div className="flex items-center space-x-2">
            <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
            <span className="text-sm font-medium text-gray-600">
              {STEP_DESCRIPTIONS[
                currentStep as keyof typeof STEP_DESCRIPTIONS
              ] || currentStep}
            </span>
          </div>
        </div>

        <div className="flex items-center justify-between">
          {steps.map((step, index) => {
            const isActive = index <= currentIndex;
            const isCurrent = index === currentIndex;
            const IconComponent = STEP_ICONS[step as keyof typeof STEP_ICONS];

            return (
              <div key={step} className="flex items-center">
                <div
                  className={`
                  progress-step flex items-center justify-center w-12 h-12 rounded-2xl border-3 relative
                  ${
                    isActive
                      ? isCurrent
                        ? "bg-gradient-to-br from-primary-500 to-primary-600 border-primary-500 text-white shadow-soft-lg active"
                        : "bg-gradient-to-br from-green-500 to-green-600 border-green-500 text-white shadow-soft"
                      : "bg-gray-100 border-gray-300 text-gray-400"
                  }
                `}
                >
                  <IconComponent className="w-5 h-5" />
                  {isCurrent && (
                    <div className="absolute -inset-1 bg-gradient-to-br from-primary-400 to-primary-600 rounded-2xl opacity-30 animate-pulse"></div>
                  )}
                </div>
                {index < steps.length - 1 && (
                  <div
                    className={`w-12 h-1 mx-2 rounded-full transition-all duration-500 ${
                      isActive
                        ? "bg-gradient-to-r from-green-400 to-green-600"
                        : "bg-gray-300"
                    }`}
                  />
                )}
              </div>
            );
          })}
        </div>

        {/* Progress percentage */}
        <div className="mt-4">
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>Progress</span>
            <span>
              {Math.round(((currentIndex + 1) / steps.length) * 100)}%
            </span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-2">
            <div
              className="bg-gradient-to-r from-primary-500 to-secondary-500 h-2 rounded-full transition-all duration-500"
              style={{ width: `${((currentIndex + 1) / steps.length) * 100}%` }}
            ></div>
          </div>
        </div>
      </div>
    );
  };

  return (
    <div className="flex flex-col h-screen bg-mesh">
      {/* Header */}
      <div className="bg-white/80 backdrop-blur-lg shadow-soft border-b border-white/20 px-6 py-6">
        <div className="flex items-center space-x-4">
          <div className="relative">
            <div className="w-12 h-12 bg-gradient-to-br from-primary-500 to-secondary-600 rounded-2xl flex items-center justify-center shadow-soft-lg">
              <Brain className="w-7 h-7 text-white" />
            </div>
            <div className="absolute -top-1 -right-1 w-4 h-4 bg-green-400 rounded-full border-2 border-white animate-pulse-soft"></div>
          </div>
          <div>
            <h1 className="text-2xl font-bold text-gradient">
              AI Research Assistant
            </h1>
            <p className="text-gray-600 font-medium">
              Intelligent research with interactive guidance
            </p>
          </div>
          {threadId && (
            <div className="ml-auto flex items-center space-x-2 bg-green-50 px-4 py-2 rounded-full border border-green-200">
              <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
              <span className="text-sm font-medium text-green-700">
                Active Session
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Progress Bar */}
      {threadId && currentStep !== "idle" && (
        <div className="px-6 py-6">{renderProgressBar()}</div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {messages.length === 0 && (
          <div className="text-center py-16 animate-fade-in">
            <div className="relative mb-8">
              <div className="w-24 h-24 bg-gradient-to-br from-primary-500 to-secondary-600 rounded-3xl flex items-center justify-center mx-auto shadow-soft-lg">
                <Brain className="w-12 h-12 text-white" />
              </div>
              <div className="absolute -top-2 -right-2 w-6 h-6 bg-yellow-400 rounded-full flex items-center justify-center animate-bounce-soft">
                <span className="text-sm">✨</span>
              </div>
            </div>
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              Welcome to AI Research Assistant
            </h2>
            <p className="text-gray-600 max-w-2xl mx-auto text-lg leading-relaxed">
              Ask me anything and I'll conduct thorough research with
              interactive guidance to provide you with comprehensive,
              well-analyzed answers.
            </p>
            <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-4 max-w-4xl mx-auto">
              <div className="p-6 bg-white/60 backdrop-blur-sm rounded-2xl border border-white/40 shadow-soft">
                <Search className="w-8 h-8 text-primary-600 mx-auto mb-3" />
                <h3 className="font-semibold text-gray-900 mb-2">
                  Deep Research
                </h3>
                <p className="text-sm text-gray-600">
                  Comprehensive information gathering from multiple sources
                </p>
              </div>
              <div className="p-6 bg-white/60 backdrop-blur-sm rounded-2xl border border-white/40 shadow-soft">
                <Brain className="w-8 h-8 text-primary-600 mx-auto mb-3" />
                <h3 className="font-semibold text-gray-900 mb-2">
                  Smart Analysis
                </h3>
                <p className="text-sm text-gray-600">
                  AI-powered synthesis and insight generation
                </p>
              </div>
              <div className="p-6 bg-white/60 backdrop-blur-sm rounded-2xl border border-white/40 shadow-soft">
                <MessageSquare className="w-8 h-8 text-primary-600 mx-auto mb-3" />
                <h3 className="font-semibold text-gray-900 mb-2">
                  Interactive Guidance
                </h3>
                <p className="text-sm text-gray-600">
                  Real-time decisions and personalized responses
                </p>
              </div>
            </div>
          </div>
        )}

        {messages.map((message, index) => (
          <div
            key={index}
            className={`flex ${
              message.role === "user" ? "justify-end" : "justify-start"
            } chat-message`}
          >
            <div
              className={`flex items-start space-x-4 max-w-4xl ${
                message.role === "user"
                  ? "flex-row-reverse space-x-reverse"
                  : ""
              }`}
            >
              <div
                className={`
                w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0 shadow-soft
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
                  <User className="w-5 h-5 text-white" />
                ) : message.role === "system" ? (
                  <AlertCircle className="w-5 h-5 text-white" />
                ) : (
                  <Bot className="w-5 h-5 text-white" />
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
                  <div className="prose prose-gray prose-lg max-w-none leading-relaxed">
                    <ReactMarkdown
                      components={{
                        p: ({ children }) => <p className="mb-4 last:mb-0 leading-relaxed">{children}</p>,
                        strong: ({ children }) => <strong className="font-bold text-gray-900">{children}</strong>,
                        em: ({ children }) => <em className="italic text-gray-700">{children}</em>,
                        code: ({ children }) => <code className="bg-gray-100 text-gray-900 px-2 py-1 rounded text-sm font-mono">{children}</code>,
                        pre: ({ children }) => <pre className="bg-gray-100 p-4 rounded-lg overflow-x-auto mb-4">{children}</pre>,
                        h1: ({ children }) => <h1 className="text-2xl font-bold text-gray-900 mb-4 mt-6 first:mt-0">{children}</h1>,
                        h2: ({ children }) => <h2 className="text-xl font-bold text-gray-900 mb-3 mt-5 first:mt-0">{children}</h2>,
                        h3: ({ children }) => <h3 className="text-lg font-bold text-gray-900 mb-2 mt-4 first:mt-0">{children}</h3>,
                        h4: ({ children }) => <h4 className="text-base font-bold text-gray-900 mb-2 mt-3 first:mt-0">{children}</h4>,
                        ul: ({ children }) => <ul className="list-disc list-inside mb-4 space-y-2 pl-4">{children}</ul>,
                        ol: ({ children }) => <ol className="list-decimal list-inside mb-4 space-y-2 pl-4">{children}</ol>,
                        li: ({ children }) => <li className="text-gray-800 leading-relaxed">{children}</li>,
                        blockquote: ({ children }) => <blockquote className="border-l-4 border-gray-300 pl-4 italic text-gray-700 mb-4">{children}</blockquote>,
                        a: ({ children, href }) => <a href={href} className="text-blue-600 hover:text-blue-800 underline" target="_blank" rel="noopener noreferrer">{children}</a>,
                        table: ({ children }) => <div className="overflow-x-auto mb-4"><table className="min-w-full border border-gray-300 rounded-lg">{children}</table></div>,
                        thead: ({ children }) => <thead className="bg-gray-50">{children}</thead>,
                        th: ({ children }) => <th className="border border-gray-300 px-4 py-2 text-left font-semibold">{children}</th>,
                        td: ({ children }) => <td className="border border-gray-300 px-4 py-2">{children}</td>,
                      }}
                    >
                      {message.content}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <div className="whitespace-pre-wrap leading-relaxed">
                    {message.content}
                  </div>
                )}
                <div
                  className={`text-xs mt-3 flex items-center space-x-2 ${
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
        ))}

        {/* Interrupt Options */}
        {interruptData && (
          <div className="interrupt-card animate-slide-up">
            <div className="flex items-center space-x-3 mb-4">
              <div className="w-8 h-8 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-xl flex items-center justify-center">
                <AlertCircle className="w-5 h-5 text-white" />
              </div>
              <h3 className="font-bold text-blue-900 text-lg">
                Research Assistant
              </h3>
            </div>
            <div className="text-blue-800 mb-6 text-lg leading-relaxed">
              <div className="prose prose-blue prose-lg max-w-none">
                <ReactMarkdown
                  components={{
                    p: ({ children }) => <p className="mb-4 last:mb-0">{children}</p>,
                    strong: ({ children }) => <strong className="font-bold text-blue-900">{children}</strong>,
                    em: ({ children }) => <em className="italic text-blue-700">{children}</em>,
                    code: ({ children }) => <code className="bg-blue-100 text-blue-900 px-2 py-1 rounded text-sm font-mono">{children}</code>,
                    h1: ({ children }) => <h1 className="text-xl font-bold text-blue-900 mb-3">{children}</h1>,
                    h2: ({ children }) => <h2 className="text-lg font-bold text-blue-900 mb-2">{children}</h2>,
                    h3: ({ children }) => <h3 className="text-base font-bold text-blue-900 mb-2">{children}</h3>,
                    ul: ({ children }) => <ul className="list-disc list-inside mb-4 space-y-1">{children}</ul>,
                    ol: ({ children }) => <ol className="list-decimal list-inside mb-4 space-y-1">{children}</ol>,
                    li: ({ children }) => <li className="text-blue-800">{children}</li>,
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
            <div className="flex items-center space-x-4">
              <div className="w-10 h-10 bg-gradient-to-br from-gray-700 to-gray-800 rounded-2xl flex items-center justify-center shadow-soft">
                <Bot className="w-5 h-5 text-white" />
              </div>
              <div className="bg-white/80 backdrop-blur-sm border border-white/40 rounded-2xl px-6 py-4 shadow-soft">
                <div className="flex items-center space-x-3">
                  <div className="relative">
                    <Loader2 className="w-5 h-5 animate-spin text-primary-600" />
                  </div>
                  <span className="text-gray-700 font-medium">
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
      <div className="bg-white/80 backdrop-blur-lg border-t border-white/20 px-6 py-6">
        <form
          onSubmit={handleSubmit}
          className="flex space-x-4 max-w-6xl mx-auto"
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
              className="input-field w-full pr-12"
              disabled={isLoading}
            />
            {input && (
              <div className="absolute right-4 top-1/2 transform -translate-y-1/2">
                <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
              </div>
            )}
          </div>
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="send-button flex items-center space-x-2"
          >
            <Send className="w-5 h-5" />
            <span className="hidden sm:inline font-medium">Send</span>
          </button>
        </form>

        {!threadId && (
          <div className="mt-4 text-center">
            <p className="text-sm text-gray-500">
              Start with questions like: "Explain quantum computing" or
              "Research the latest AI trends"
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
