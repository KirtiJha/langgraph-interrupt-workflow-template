"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Bot, Database, Plus, Rocket, TriangleAlert, X } from "lucide-react";
import Gallery from "../components/Gallery";
import ModelSettingsButton from "../components/ModelSettings";
import Workspace from "../components/Workspace";
import { API_URL, Mission, World, getJSON } from "../lib/api";
import { useModelSettings } from "../lib/modelSettings";
import { savedThread, useMission } from "../lib/useMission";

const PREFS_KEY = "mc_prefs";

export default function Page() {
  const { ui, start, decide, followUp, loadHistory, fork, pause, restore, leave, clearError } = useMission();
  const userModel = useModelSettings();
  const [capabilities, setCapabilities] = useState<any | null>(null);
  const [backendDown, setBackendDown] = useState(false);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [world, setWorld] = useState<World | null>(null);
  const [memories, setMemories] = useState<string[]>([]);
  const [userId, setUserId] = useState<string | null>(null);
  const [autonomy, setAutonomy] = useState("careful");
  const [askAbove, setAskAbove] = useState(100);
  const [resumable, setResumable] = useState<{ threadId: string; title: string } | null>(null);
  const inMission = ui.feed.length > 0;

  useEffect(() => {
    try {
      let id = localStorage.getItem("lg_user_id");
      if (!id) { id = `user-${Math.random().toString(36).slice(2, 10)}`; localStorage.setItem("lg_user_id", id); }
      setUserId(id);
      const prefs = JSON.parse(localStorage.getItem(PREFS_KEY) || "{}");
      if (prefs.autonomy) setAutonomy(prefs.autonomy);
      if (prefs.askAbove != null) setAskAbove(prefs.askAbove);
      setResumable(savedThread());
    } catch { setUserId("anon"); }
  }, []);

  useEffect(() => {
    try { localStorage.setItem(PREFS_KEY, JSON.stringify({ autonomy, askAbove })); } catch { /* ignore */ }
  }, [autonomy, askAbove]);

  const loadMeta = useCallback(() => {
    getJSON("/capabilities").then((c) => { setCapabilities(c); setBackendDown(false); }).catch(() => setBackendDown(true));
    if (userId) getJSON(`/missions?user_id=${encodeURIComponent(userId)}`).then((d) => { setMissions(d.missions); setWorld(d.world); setMemories(d.memories); }).catch(() => {});
  }, [userId]);
  useEffect(() => { loadMeta(); }, [loadMeta]);
  useEffect(() => { if (ui.status === "completed") loadMeta(); }, [ui.status, loadMeta]); // refresh memories

  const launch = (goal: string, mission: Mission | null) => {
    setResumable(null);
    start(goal, { missionId: mission?.id ?? null, title: mission?.title ?? goal, userId, autonomy, askAbove });
  };

  const resume = async () => {
    if (!resumable) return;
    try { await restore(resumable.threadId, resumable.title); } catch { setResumable(null); leave(); }
  };

  const model = capabilities?.model;
  const persistence = capabilities?.persistence;
  const offlinePilot = userModel ? userModel.provider === "mock" : !!capabilities?.offline_pilot;

  return (
    <div className="flex min-h-[100dvh] flex-col lg:h-[100dvh]">
      <header className="sticky top-0 z-20 border-b border-stone-200/70 bg-paper/85 backdrop-blur">
        <div className="mx-auto flex max-w-[1480px] items-center gap-3 px-4 py-2.5">
          <button type="button" onClick={() => inMission && leave()} className="flex items-center gap-2" aria-label="Mission Control home">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-ink text-paper"><Rocket className="h-4 w-4" aria-hidden="true" /></span>
            <span className="hidden text-[15px] font-semibold tracking-tight text-ink sm:inline">Mission Control</span>
          </button>
          <div className="ml-auto flex items-center gap-2">
            {capabilities && (
              <>
                <span className={`chip hidden sm:inline-flex ${offlinePilot ? "border-stone-200 bg-stone-50 text-stone-600" : "border-emerald-200 bg-emerald-50 text-emerald-700"}`}
                      title={offlinePilot ? "Offline pilot: starter missions run without a key. Add a model for your own goals." : `Model: ${userModel?.model || model?.name}`}>
                  <Bot className="h-3 w-3" aria-hidden="true" />{userModel ? (userModel.provider === "mock" ? "Offline pilot" : userModel.model) : model?.mock ? "Offline pilot" : model?.name}
                </span>
                <span className={`chip hidden md:inline-flex ${persistence?.multi_instance_safe ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-stone-200 bg-stone-50 text-stone-600"}`}
                      title={persistence?.multi_instance_safe ? "Missions are stored in Postgres: pause for days, resume from anywhere." : "In-memory state: a restart loses paused missions. Set DATABASE_URL."}>
                  <Database className="h-3 w-3" aria-hidden="true" />{persistence?.checkpointer === "postgres" ? "Postgres" : persistence?.checkpointer === "sqlite" ? "SQLite" : "In-memory"}
                </span>
              </>
            )}
            <ModelSettingsButton apiUrl={API_URL} />
            {inMission && (
              <button type="button" onClick={leave} className="btn-outline h-8 px-2.5 text-xs" aria-label="New mission"><Plus className="h-3.5 w-3.5" aria-hidden="true" /><span className="hidden sm:inline">New mission</span></button>
            )}
          </div>
        </div>
      </header>

      {backendDown && (
        <div role="alert" className="flex flex-wrap items-center gap-2 border-b border-rose-200 bg-rose-50 px-4 py-2 text-xs text-rose-800">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          <span>Can't reach the backend at <code className="font-mono">{API_URL}</code>. Start it with <code className="font-mono">cd backend && python main.py</code>.</span>
          <button type="button" onClick={loadMeta} className="ml-auto rounded-full border border-rose-300 bg-white px-3 py-1 font-medium text-rose-700 hover:bg-rose-100">Retry</button>
        </div>
      )}
      {ui.error && (
        <div role="alert" className="flex items-start gap-2 border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900">
          <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" /><span className="flex-1">{ui.error}</span>
          <button type="button" onClick={clearError} aria-label="Dismiss" className="rounded p-0.5 hover:bg-amber-100"><X className="h-3.5 w-3.5" aria-hidden="true" /></button>
        </div>
      )}

      {inMission ? (
        <Workspace ui={ui} onDecide={decide} onFollowUp={followUp} onFork={fork} onLoadHistory={loadHistory} onPause={pause} />
      ) : (
        <>
          {resumable && (
            <div className="mx-auto mt-4 flex w-full max-w-6xl items-center gap-3 px-4">
              <div className="flex flex-1 flex-wrap items-center gap-2 rounded-xl border border-ember-200 bg-ember-50 px-3 py-2 text-sm text-ember-900">
                <span>You have a mission in progress: <strong>{resumable.title}</strong>.</span>
                <button type="button" onClick={resume} className="btn-accent h-8 px-3 text-xs">Resume</button>
                <button type="button" onClick={() => { setResumable(null); leave(); }} className="btn-ghost h-8 px-2 text-xs">Discard</button>
              </div>
            </div>
          )}
          <Gallery missions={missions} world={world} memories={memories} offlinePilot={offlinePilot}
                   autonomy={autonomy} askAbove={askAbove} onAutonomy={setAutonomy} onAskAbove={setAskAbove}
                   onStart={launch} busy={ui.streaming} />
        </>
      )}
    </div>
  );
}
