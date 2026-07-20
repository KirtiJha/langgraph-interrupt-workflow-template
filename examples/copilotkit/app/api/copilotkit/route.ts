/**
 * CopilotKit runtime route — bridges the CopilotKit frontend to the template's
 * agent over the AG-UI protocol.
 *
 * The template's FastAPI backend exposes the agent at `/agui` (see
 * `backend/agui.py`). Here we register it as an AG-UI `HttpAgent` on a
 * `CopilotRuntime` and expose that runtime at `/api/copilotkit`, which the
 * `<CopilotKit>` provider on the page talks to.
 *
 * No LLM key is needed in *this* app — the model lives in the Python backend.
 */
import {
  CopilotRuntime,
  ExperimentalEmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";
import { HttpAgent } from "@ag-ui/client";

export const runtime = "nodejs";

// Where the template's AG-UI endpoint lives. Override in .env.
const AGUI_URL = process.env.AGUI_URL ?? "http://127.0.0.1:8000/agui";

const copilotRuntime = new CopilotRuntime({
  agents: {
    // Must match the `agent` prop on <CopilotKit> in app/page.tsx.
    research_agent: new HttpAgent({ url: AGUI_URL }),
  },
});

export const POST = async (req: Request) => {
  const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
    runtime: copilotRuntime,
    serviceAdapter: new ExperimentalEmptyAdapter(),
    endpoint: "/api/copilotkit",
  });
  return handleRequest(req);
};
