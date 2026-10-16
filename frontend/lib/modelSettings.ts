"use client";

// Model settings chosen in the browser ("bring your own model and key").
//
// They travel to the backend as X-LLM-* headers on every API call, where they
// apply to that request only — nothing is stored server-side. The key stays in
// this browser: sessionStorage by default (gone when the tab closes), or
// localStorage when the user ticks "Remember on this device".

import { useEffect, useState } from "react";

export interface ModelSettings {
  provider: string; // preset id from GET /model/providers (e.g. "anthropic")
  model: string;
  apiKey?: string;
  baseUrl?: string; // custom OpenAI-compatible endpoints only
  temperature?: string; // kept as typed; blank = provider default
}

export interface ProviderPreset {
  id: string;
  label: string;
  base_url: string | null;
  key_label: string | null;
  models: string[];
  key_optional?: boolean;
  custom_base_url?: boolean;
  note?: string;
}

const KEY = "lg_model_settings";
const EVENT = "lg-model-settings";

function read(store: Storage | undefined): ModelSettings | null {
  try {
    const raw = store?.getItem(KEY);
    return raw ? (JSON.parse(raw) as ModelSettings) : null;
  } catch {
    return null;
  }
}

function storages(): { session?: Storage; local?: Storage } {
  if (typeof window === "undefined") return {};
  try {
    return { session: window.sessionStorage, local: window.localStorage };
  } catch {
    return {}; // storage blocked (private mode / disabled cookies)
  }
}

export function loadModelSettings(): ModelSettings | null {
  const { session, local } = storages();
  return read(session) ?? read(local);
}

export function isRemembered(): boolean {
  return read(storages().local) !== null;
}

export function saveModelSettings(settings: ModelSettings, remember: boolean) {
  const { session, local } = storages();
  const raw = JSON.stringify(settings);
  try {
    session?.setItem(KEY, raw);
    if (remember) local?.setItem(KEY, raw);
    else local?.removeItem(KEY);
  } catch {
    /* storage full / blocked: settings still apply until reload via the event */
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: settings }));
}

export function clearModelSettings() {
  const { session, local } = storages();
  try {
    session?.removeItem(KEY);
    local?.removeItem(KEY);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: null }));
}

/** Headers carrying the browser's model choice; empty = use the server's model. */
export function llmHeaders(settings?: ModelSettings | null): Record<string, string> {
  const s = settings === undefined ? loadModelSettings() : settings;
  if (!s?.provider) return {};
  const headers: Record<string, string> = { "X-LLM-Provider": s.provider };
  if (s.model) headers["X-LLM-Model"] = s.model;
  if (s.apiKey) headers["X-LLM-API-Key"] = s.apiKey;
  if (s.baseUrl) headers["X-LLM-Base-URL"] = s.baseUrl;
  if (s.temperature?.trim()) headers["X-LLM-Temperature"] = s.temperature.trim();
  return headers;
}

/** JSON request headers plus the model choice — use for every model-backed call. */
export function apiHeaders(): Record<string, string> {
  return { "Content-Type": "application/json", ...llmHeaders() };
}

/** Current settings, kept in sync when the settings dialog saves or clears. */
export function useModelSettings(): ModelSettings | null {
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  useEffect(() => {
    setSettings(loadModelSettings());
    const onChange = (e: Event) => setSettings((e as CustomEvent).detail ?? null);
    window.addEventListener(EVENT, onChange);
    return () => window.removeEventListener(EVENT, onChange);
  }, []);
  return settings;
}

/** An error whose message is safe and useful to show (e.g. "Model settings: …"). */
export class ApiError extends Error {}

/** Throw an ApiError carrying the backend's `detail` for a failed response. */
export async function ensureOk(res: Response): Promise<Response> {
  if (res.ok) return res;
  let detail = `HTTP ${res.status}`;
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") detail = body.detail;
  } catch {
    /* not JSON */
  }
  throw new ApiError(detail);
}

/** The message to show for a failed call: the model-settings reason, or a fallback. */
export function describeError(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.message.startsWith("Model settings:")) {
    return `${error.message} Open ⚙ Model to fix it.`;
  }
  return fallback;
}
