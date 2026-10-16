"use client";

// The visitor's GitHub token ("Connect"): kept in this browser, sent as the
// X-GitHub-Token header on each request, never stored on the server.

import { useEffect, useState } from "react";

const KEY = "rs_github_token";
const EVENT = "rs-github-token";

function storages(): { session?: Storage; local?: Storage } {
  if (typeof window === "undefined") return {};
  try {
    return { session: window.sessionStorage, local: window.localStorage };
  } catch {
    return {};
  }
}

export function loadGitHubToken(): string | null {
  const { session, local } = storages();
  try {
    return session?.getItem(KEY) || local?.getItem(KEY) || null;
  } catch {
    return null;
  }
}

export function isTokenRemembered(): boolean {
  try {
    return !!storages().local?.getItem(KEY);
  } catch {
    return false;
  }
}

export function saveGitHubToken(token: string, remember: boolean) {
  const { session, local } = storages();
  try {
    session?.setItem(KEY, token);
    if (remember) local?.setItem(KEY, token);
    else local?.removeItem(KEY);
  } catch {
    /* storage blocked */
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: token }));
}

export function clearGitHubToken() {
  const { session, local } = storages();
  try {
    session?.removeItem(KEY);
    local?.removeItem(KEY);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new CustomEvent(EVENT, { detail: null }));
}

export function githubHeaders(): Record<string, string> {
  const token = loadGitHubToken();
  return token ? { "X-GitHub-Token": token } : {};
}

export function useGitHubToken(): string | null {
  const [token, setToken] = useState<string | null>(null);
  useEffect(() => {
    setToken(loadGitHubToken());
    const onChange = (e: Event) => setToken((e as CustomEvent).detail ?? null);
    window.addEventListener(EVENT, onChange);
    return () => window.removeEventListener(EVENT, onChange);
  }, []);
  return token;
}

/** Recently used repositories, most recent first. */
export function recentRepos(): string[] {
  try {
    return JSON.parse(localStorage.getItem("rs_recent_repos") || "[]");
  } catch {
    return [];
  }
}

export function rememberRepo(slug: string) {
  try {
    const list = [slug, ...recentRepos().filter((r) => r !== slug)].slice(0, 6);
    localStorage.setItem("rs_recent_repos", JSON.stringify(list));
  } catch {
    /* ignore */
  }
}
