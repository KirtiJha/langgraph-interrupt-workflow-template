"use client";

import { CopilotKit } from "@copilotkit/react-core";
import { CopilotChat } from "@copilotkit/react-ui";
import "@copilotkit/react-ui/styles.css";

/**
 * A CopilotKit chat wired to the template's agent over AG-UI.
 *
 * `runtimeUrl` points at the local runtime route (app/api/copilotkit), and
 * `agent` selects the AG-UI agent registered there. Because the agent pauses
 * for human approval before running a tool, CopilotKit surfaces that pause in
 * the chat — the same human-in-the-loop flow as the bundled UI, but driven by a
 * standard protocol.
 */
export default function Page() {
  return (
    <main style={{ height: "100dvh", display: "flex", flexDirection: "column" }}>
      <header
        style={{
          padding: "12px 16px",
          borderBottom: "1px solid #eee",
          fontFamily: "system-ui, sans-serif",
        }}
      >
        <strong>CopilotKit × AG-UI</strong>{" "}
        <span style={{ color: "#888", fontSize: 13 }}>
          — the human-in-the-loop agent, driven over the AG-UI protocol
        </span>
      </header>
      <div style={{ flex: 1, minHeight: 0 }}>
        <CopilotKit runtimeUrl="/api/copilotkit" agent="research_agent">
          <CopilotChat
            labels={{
              title: "HITL Research Agent",
              initial:
                "Ask me to research something — I'll pause for your approval before I search.",
            }}
            className="h-full"
          />
        </CopilotKit>
      </div>
    </main>
  );
}
