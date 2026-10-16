"use client";

// "⚙ Model" button + dialog: pick a provider, model and key in the browser.
// The choice is sent as X-LLM-* headers (see lib/modelSettings.ts) and applies
// to this browser only; clearing it goes back to the server's default model.

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AlertCircle, CheckCircle, KeyRound, Loader2, Settings2, X } from "lucide-react";
import {
  ModelSettings,
  ProviderPreset,
  clearModelSettings,
  isRemembered,
  llmHeaders,
  saveModelSettings,
  useModelSettings,
} from "../lib/modelSettings";

interface Policy {
  enabled: boolean;
  server_key_shared: boolean;
  private_hosts_allowed: boolean;
}

interface ServerDefault {
  mock?: boolean;
  name?: string | null;
  error?: string | null;
}

type TestResult = { ok: boolean; latency_ms?: number; sample?: string; error?: string } | null;

const field =
  "w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ember-500";

export default function ModelSettingsButton({ apiUrl }: { apiUrl: string }) {
  const active = useModelSettings();
  const [open, setOpen] = useState(false);
  const [providers, setProviders] = useState<ProviderPreset[]>([]);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [serverDefault, setServerDefault] = useState<ServerDefault | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [draft, setDraft] = useState<ModelSettings>({ provider: "", model: "" });
  const [remember, setRemember] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<TestResult>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  const preset = providers.find((p) => p.id === draft.provider);

  // Load presets the first time the dialog opens.
  useEffect(() => {
    if (!open || providers.length) return;
    fetch(`${apiUrl}/model/providers`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data) => {
        setProviders(data.providers || []);
        setPolicy(data.policy || null);
        setServerDefault(data.server_default || null);
        setLoadError(null);
      })
      .catch(() => setLoadError(`Couldn't load providers from ${apiUrl}.`));
  }, [open, apiUrl, providers.length]);

  // Opening the dialog starts from what's saved.
  useEffect(() => {
    if (!open) return;
    setDraft(active ?? { provider: "", model: "" });
    setRemember(isRemembered());
    setResult(null);
    setShowKey(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // Escape closes; focus moves into the dialog.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    dialogRef.current?.querySelector<HTMLElement>("select, input, button")?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const pickProvider = (id: string) => {
    const next = providers.find((p) => p.id === id);
    setDraft((d) => ({
      provider: id,
      // Keep a typed model if it fits the new provider's list, else suggest its first.
      model: next?.models.includes(d.model) ? d.model : next?.models[0] ?? "",
      apiKey: d.provider === id ? d.apiKey : "",
      baseUrl: next?.custom_base_url ? d.baseUrl ?? "" : undefined,
      temperature: d.temperature,
    }));
    setResult(null);
  };

  const keyNeeded = !!preset && !preset.key_optional && !policy?.server_key_shared;
  const missing =
    !draft.provider
      ? "Choose a provider."
      : !draft.model.trim()
      ? "Enter a model."
      : preset?.custom_base_url && !draft.baseUrl?.trim()
      ? "Enter the base URL."
      : keyNeeded && !draft.apiKey?.trim()
      ? `Enter your ${preset?.key_label ?? "API key"}.`
      : null;

  const clean = (): ModelSettings => ({
    provider: draft.provider,
    model: draft.model.trim(),
    apiKey: draft.apiKey?.trim() || undefined,
    baseUrl: preset?.custom_base_url ? draft.baseUrl?.trim() || undefined : undefined,
    temperature: draft.temperature?.trim() || undefined,
  });

  const test = async () => {
    if (missing) return;
    setTesting(true);
    setResult(null);
    try {
      const res = await fetch(`${apiUrl}/model/test`, {
        method: "POST",
        headers: llmHeaders(clean()),
      });
      const data = await res.json().catch(() => ({}));
      setResult(res.ok ? data : { ok: false, error: data?.detail || `HTTP ${res.status}` });
    } catch {
      setResult({ ok: false, error: `Couldn't reach ${apiUrl}.` });
    } finally {
      setTesting(false);
    }
  };

  const save = () => {
    if (missing) return;
    saveModelSettings(clean(), remember);
    setOpen(false);
  };

  const reset = () => {
    clearModelSettings();
    setOpen(false);
  };

  const label = active
    ? active.provider === "mock"
      ? "Mock model"
      : active.model
    : "Server model";

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        title={
          active
            ? `Using your model: ${active.model} (${active.provider}) — click to change`
            : "Choose the model and provider (bring your own key)"
        }
        className={`flex items-center gap-1 max-w-[12rem] text-xs font-medium rounded-full px-3 py-1.5 border transition-colors ${
          active
            ? "bg-ember-50 hover:bg-ember-100 border-ember-200 text-ember-700"
            : "bg-gray-50 hover:bg-gray-100 border-gray-200 text-gray-600 hover:text-gray-900"
        }`}
      >
        <Settings2 className="w-3.5 h-3.5 shrink-0" aria-hidden="true" />
        <span className="truncate">{label}</span>
      </button>

      {/* Portal: the header's backdrop-blur would otherwise trap this fixed overlay. */}
      {open && createPortal(
        <div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/30 p-0 sm:p-4"
          onMouseDown={(e) => e.target === e.currentTarget && setOpen(false)}
        >
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="model-settings-title"
            className="w-full sm:max-w-md max-h-[90dvh] overflow-y-auto rounded-t-2xl sm:rounded-2xl bg-paper shadow-lift p-5"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 id="model-settings-title" className="text-base font-semibold text-gray-900">
                  Model settings
                </h2>
                <p className="mt-0.5 text-xs text-gray-500">
                  Use any provider with your own key. Applies to this browser only.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="rounded-full p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-700"
              >
                <X className="w-4 h-4" aria-hidden="true" />
              </button>
            </div>

            {loadError && (
              <p role="alert" className="mt-4 rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">
                {loadError}
              </p>
            )}
            {policy && !policy.enabled && (
              <p className="mt-4 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
                This server ignores model settings from the browser (LLM_CLIENT_CONFIG=false) and
                always uses its own model.
              </p>
            )}

            <div className="mt-4 space-y-3">
              <label className="block">
                <span className="text-xs font-medium text-gray-700">Provider</span>
                <select
                  aria-label="Provider"
                  className={`${field} mt-1`}
                  value={draft.provider}
                  onChange={(e) => pickProvider(e.target.value)}
                >
                  <option value="">
                    Server default
                    {serverDefault
                      ? ` (${serverDefault.mock ? "mock model" : serverDefault.name})`
                      : ""}
                  </option>
                  {providers.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                </select>
                {preset?.note && <span className="mt-1 block text-[11px] text-gray-500">{preset.note}</span>}
              </label>

              {preset && preset.id !== "mock" && (
                <>
                  <label className="block">
                    <span className="text-xs font-medium text-gray-700">Model</span>
                    <input
                      aria-label="Model"
                      className={`${field} mt-1 font-mono`}
                      list="model-suggestions"
                      value={draft.model}
                      onChange={(e) => setDraft({ ...draft, model: e.target.value })}
                      placeholder={preset.models[0] ?? "model-id"}
                      autoComplete="off"
                      spellCheck={false}
                    />
                    <datalist id="model-suggestions">
                      {preset.models.map((m) => (
                        <option key={m} value={m} />
                      ))}
                    </datalist>
                    <span className="mt-1 block text-[11px] text-gray-500">
                      Pick a suggestion or type any model id the provider offers.
                    </span>
                  </label>

                  {preset.custom_base_url && (
                    <label className="block">
                      <span className="text-xs font-medium text-gray-700">Base URL</span>
                      <input
                        aria-label="Base URL"
                        className={`${field} mt-1 font-mono`}
                        value={draft.baseUrl ?? ""}
                        onChange={(e) => setDraft({ ...draft, baseUrl: e.target.value })}
                        placeholder="https://my-endpoint.example.com/v1"
                        inputMode="url"
                        autoComplete="off"
                        spellCheck={false}
                      />
                      {policy && !policy.private_hosts_allowed && (
                        <span className="mt-1 block text-[11px] text-gray-500">
                          Must be a public https endpoint on this deployment.
                        </span>
                      )}
                    </label>
                  )}

                  <label className="block">
                    <span className="text-xs font-medium text-gray-700">
                      {preset.key_label ?? "API key"}
                      {!keyNeeded && <span className="font-normal text-gray-400"> (optional)</span>}
                    </span>
                    <div className="mt-1 flex gap-2">
                      <input
                        aria-label="API key"
                        className={`${field} font-mono`}
                        type={showKey ? "text" : "password"}
                        value={draft.apiKey ?? ""}
                        onChange={(e) => setDraft({ ...draft, apiKey: e.target.value })}
                        placeholder={keyNeeded ? "Required" : "Uses the server's key"}
                        autoComplete="off"
                        spellCheck={false}
                      />
                      <button
                        type="button"
                        onClick={() => setShowKey((v) => !v)}
                        aria-pressed={showKey}
                        className="shrink-0 rounded-lg border border-gray-200 px-2 text-xs text-gray-600 hover:bg-gray-50"
                      >
                        {showKey ? "Hide" : "Show"}
                      </button>
                    </div>
                    <span className="mt-1 flex items-start gap-1 text-[11px] text-gray-500">
                      <KeyRound className="mt-px w-3 h-3 shrink-0" aria-hidden="true" />
                      Sent with each request to this app's backend, never stored there.
                    </span>
                  </label>

                  <label className="block">
                    <span className="text-xs font-medium text-gray-700">
                      Temperature <span className="font-normal text-gray-400">(optional)</span>
                    </span>
                    <input
                      aria-label="Temperature"
                      className={`${field} mt-1 w-28`}
                      inputMode="decimal"
                      value={draft.temperature ?? ""}
                      onChange={(e) => setDraft({ ...draft, temperature: e.target.value })}
                      placeholder="default"
                    />
                  </label>

                  <label className="flex items-center gap-2 text-xs text-gray-700">
                    <input
                      type="checkbox"
                      checked={remember}
                      onChange={(e) => setRemember(e.target.checked)}
                      className="rounded border-gray-300"
                    />
                    Remember on this device (otherwise cleared when the tab closes)
                  </label>
                </>
              )}
            </div>

            {result && (
              <div
                role="status"
                className={`mt-4 flex items-start gap-2 rounded-lg px-3 py-2 text-xs ${
                  result.ok ? "bg-green-50 text-green-800" : "bg-rose-50 text-rose-700"
                }`}
              >
                {result.ok ? (
                  <CheckCircle className="mt-px w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                ) : (
                  <AlertCircle className="mt-px w-3.5 h-3.5 shrink-0" aria-hidden="true" />
                )}
                <span className="break-words min-w-0">
                  {result.ok
                    ? `Connected in ${result.latency_ms} ms${result.sample ? ` — “${result.sample}”` : ""}`
                    : result.error}
                </span>
              </div>
            )}

            <div className="mt-5 flex flex-wrap items-center gap-2">
              {active && (
                <button
                  type="button"
                  onClick={reset}
                  className="text-xs font-medium text-gray-500 hover:text-gray-800 underline-offset-2 hover:underline"
                >
                  Use server default
                </button>
              )}
              <div className="ml-auto flex gap-2">
                {preset && (
                  <button
                    type="button"
                    onClick={test}
                    disabled={!!missing || testing}
                    className="flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                  >
                    {testing && <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />}
                    Test connection
                  </button>
                )}
                <button
                  type="button"
                  onClick={draft.provider ? save : reset}
                  disabled={!!draft.provider && !!missing}
                  title={draft.provider ? missing ?? undefined : undefined}
                  className="rounded-lg bg-gradient-to-r from-ember-600 to-ember-600 px-4 py-2 text-xs font-medium text-white shadow-card hover:from-ember-700 hover:to-ember-700 disabled:opacity-50"
                >
                  Save
                </button>
              </div>
            </div>
            {draft.provider && missing && (
              <p className="mt-2 text-right text-[11px] text-gray-500">{missing}</p>
            )}
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
