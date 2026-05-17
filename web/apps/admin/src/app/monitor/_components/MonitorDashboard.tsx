"use client";

import { useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";

// ── Types ──────────────────────────────────────────────────────────────────────

type LiveEvent =
  | { type: "asr"; sessionId: string; agentName: string; text: string; ts: number }
  | { type: "llm_sentence"; sessionId: string; sentence: string; hanlo: string; taibun: string; ts: number }
  | { type: "tts_first_audio"; sessionId: string; latencyMs: number; ts: number }
  | { type: "turn_done"; sessionId: string; fullResponse: string; latencyAsrMs: number | null; latencyLlmFirstTokMs: number | null; latencyFirstAudioMs: number | null; wasBargedIn: boolean; errorFlag: string | null; ts: number };

type Stats = {
  activeSessions: number;
  avgFirstAudioMs: number | null;
  avgLlmFirstTokMs: number | null;
  avgAsrMs: number | null;
  errorRate: number;
};

// One conversation = one group of events with the same session burst
type ConversationTurn = {
  id: string; // unique per turn (sessionId + ts)
  sessionId: string;
  agentName: string;
  asr: string;
  sentences: { sentence: string; hanlo: string; taibun: string }[];
  latencyFirstAudioMs: number | null;
  latencyLlmFirstTokMs: number | null;
  latencyAsrMs: number | null;
  wasBargedIn: boolean;
  errorFlag: string | null;
  done: boolean;
  ts: number;
};

const MAX_TURNS = 50;

// ── Component ─────────────────────────────────────────────────────────────────

export default function MonitorDashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [turns, setTurns] = useState<ConversationTurn[]>([]);
  const [connected, setConnected] = useState(false);
  // pending: turnId → turn. activeTurnId: sessionId → current turnId.
  // Two-map approach avoids barge-in race where sessionId key would get overwritten.
  const pending = useRef<Map<string, ConversationTurn>>(new Map());
  const activeTurnId = useRef<Map<string, string>>(new Map());

  useEffect(() => {
    const es = new EventSource("/api/monitor/stream");

    es.addEventListener("stats", (e) => {
      setStats(JSON.parse(e.data) as Stats);
    });

    es.addEventListener("history", (e) => {
      type HistoryEntry = {
        id: string; sessionId: string; agentName: string;
        asr: string; llmRaw: string; hanlo: string | null; taibun: string;
        latencyFirstAudioMs: number | null; latencyLlmFirstTokMs: number | null;
        latencyAsrMs: number | null; wasBargedIn: boolean;
        errorFlag: string | null; ts: number;
      };
      const history = JSON.parse(e.data) as HistoryEntry[];
      const historicTurns: ConversationTurn[] = history.map((h) => ({
        id: h.id,
        sessionId: h.sessionId,
        agentName: h.agentName,
        asr: h.asr,
        sentences: h.llmRaw
          ? [{ sentence: h.llmRaw, hanlo: h.hanlo ?? "", taibun: h.taibun }]
          : [],
        latencyFirstAudioMs: h.latencyFirstAudioMs,
        latencyLlmFirstTokMs: h.latencyLlmFirstTokMs,
        latencyAsrMs: h.latencyAsrMs,
        wasBargedIn: h.wasBargedIn,
        errorFlag: h.errorFlag,
        done: true,
        ts: h.ts,
      }));
      setTurns(historicTurns);
    });

    es.addEventListener("live", (e) => {
      const event = JSON.parse(e.data) as LiveEvent;
      handleLiveEvent(event);
    });

    es.onopen = () => setConnected(true);
    es.onerror = () => setConnected(false);

    return () => es.close();
  }, []);

  function handleLiveEvent(event: LiveEvent) {
    if (event.type === "asr") {
      const turnId = `${event.sessionId}-${event.ts}`;

      // Barge-in: finalize any prior pending turn for this session
      const prevTurnId = activeTurnId.current.get(event.sessionId);
      if (prevTurnId) {
        const prevTurn = pending.current.get(prevTurnId);
        if (prevTurn) {
          const finalized = { ...prevTurn, wasBargedIn: true, done: true };
          pending.current.delete(prevTurnId);
          setTurns((prev) => prev.map((t) => (t.id === prevTurnId ? finalized : t)));
        }
      }

      const turn: ConversationTurn = {
        id: turnId,
        sessionId: event.sessionId,
        agentName: event.agentName,
        asr: event.text,
        sentences: [],
        latencyFirstAudioMs: null,
        latencyLlmFirstTokMs: null,
        latencyAsrMs: null,
        wasBargedIn: false,
        errorFlag: null,
        done: false,
        ts: event.ts,
      };
      pending.current.set(turnId, turn);
      activeTurnId.current.set(event.sessionId, turnId);
      setTurns((prev) => [turn, ...prev].slice(0, MAX_TURNS));
    } else if (event.type === "llm_sentence") {
      const turnId = activeTurnId.current.get(event.sessionId);
      const turn = turnId ? pending.current.get(turnId) : undefined;
      if (turnId && turn) {
        const updated = {
          ...turn,
          sentences: [
            ...turn.sentences,
            { sentence: event.sentence, hanlo: event.hanlo, taibun: event.taibun },
          ],
        };
        pending.current.set(turnId, updated);
        setTurns((prev) => prev.map((t) => (t.id === turnId ? updated : t)));
      }
    } else if (event.type === "tts_first_audio") {
      const turnId = activeTurnId.current.get(event.sessionId);
      const turn = turnId ? pending.current.get(turnId) : undefined;
      if (turnId && turn) {
        const updated = { ...turn, latencyFirstAudioMs: event.latencyMs };
        pending.current.set(turnId, updated);
        setTurns((prev) => prev.map((t) => (t.id === turnId ? updated : t)));
      }
    } else if (event.type === "turn_done") {
      const turnId = activeTurnId.current.get(event.sessionId);
      const turn = turnId ? pending.current.get(turnId) : undefined;
      if (turnId && turn) {
        const updated: ConversationTurn = {
          ...turn,
          latencyAsrMs: event.latencyAsrMs,
          latencyLlmFirstTokMs: event.latencyLlmFirstTokMs,
          latencyFirstAudioMs: event.latencyFirstAudioMs ?? turn.latencyFirstAudioMs,
          wasBargedIn: event.wasBargedIn,
          errorFlag: event.errorFlag,
          done: true,
        };
        pending.current.delete(turnId);
        activeTurnId.current.delete(event.sessionId);
        setTurns((prev) => prev.map((t) => (t.id === turnId ? updated : t)));
      }
    }
  }

  return (
    <div>
      {/* Connection status */}
      <div className="flex items-center gap-2 text-sm mb-6">
        <span className={`w-2 h-2 rounded-full ${connected ? "bg-green-400 animate-pulse" : "bg-red-400"}`} />
        <span className="text-muted-foreground">{connected ? "串流連線中" : "未連線"}</span>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 gap-3 mb-6 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label="進行中 Session" value={stats ? String(stats.activeSessions) : "—"}
          color={stats?.activeSessions ? "green" : "gray"} />
        <StatCard label="首音延遲均值"
          value={stats?.avgFirstAudioMs != null ? `${stats.avgFirstAudioMs} ms` : "—"}
          color={stats?.avgFirstAudioMs == null ? "gray" : stats.avgFirstAudioMs < 1200 ? "green" : stats.avgFirstAudioMs < 2500 ? "yellow" : "red"} />
        <StatCard label="LLM 首字均值"
          value={stats?.avgLlmFirstTokMs != null ? `${stats.avgLlmFirstTokMs} ms` : "—"}
          color={stats?.avgLlmFirstTokMs == null ? "gray" : stats.avgLlmFirstTokMs < 800 ? "green" : stats.avgLlmFirstTokMs < 1500 ? "yellow" : "red"} />
        <StatCard label="ASR 均值"
          value={stats?.avgAsrMs != null ? `${stats.avgAsrMs} ms` : "—"}
          color={stats?.avgAsrMs == null ? "gray" : stats.avgAsrMs < 600 ? "green" : stats.avgAsrMs < 1200 ? "yellow" : "red"} />
        <StatCard label="錯誤率（近 100 輪）"
          value={stats ? `${stats.errorRate}%` : "—"}
          color={!stats ? "gray" : stats.errorRate === 0 ? "green" : stats.errorRate < 5 ? "yellow" : "red"} />
      </div>


      {/* Live feed */}
      <h2 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
        對話串流
      </h2>

      {turns.length === 0 && (
        <p className="text-muted-foreground text-sm py-10 text-center">等待對話…</p>
      )}

      <div className="space-y-3">
        {turns.map((t) => (
          <TurnCard key={t.id} turn={t} />
        ))}
      </div>
    </div>
  );
}

// ── TurnCard ──────────────────────────────────────────────────────────────────

function TurnCard({ turn }: { turn: ConversationTurn }) {
  const [expanded, setExpanded] = useState(false);

  const ts = new Date(turn.ts * 1000).toLocaleTimeString("zh-TW", {
    timeZone: "Asia/Taipei",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <div className={`rounded-lg border ${
      turn.errorFlag ? "border-destructive/30 bg-destructive/5" :
      turn.wasBargedIn ? "border-amber-500/30 bg-amber-500/5" :
      "border-border bg-card"
    }`}>
      {/* Top bar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b border-inherit">
        <span className="text-xs text-muted-foreground tabular-nums">{ts}</span>
        <span className="text-xs font-medium text-foreground">{turn.agentName}</span>
        {!turn.done && (
          <span className="flex items-center gap-1 text-xs text-indigo-500">
            <span className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-pulse" />
            進行中
          </span>
        )}
        {turn.wasBargedIn && <Badge variant="outline" className="text-amber-600 border-amber-300 text-xs">打斷</Badge>}
        {turn.errorFlag && <Badge variant="outline" className="text-destructive border-destructive/30 text-xs cursor-help" title={turn.errorFlag}>{turn.errorFlag}</Badge>}

        {/* Latencies — right aligned */}
        <div className="ml-auto flex items-center gap-3 text-xs">
          {turn.latencyFirstAudioMs != null && (
            <Latency label="首音" ms={turn.latencyFirstAudioMs} />
          )}
          {turn.latencyLlmFirstTokMs != null && (
            <Latency label="LLM 首字" ms={turn.latencyLlmFirstTokMs} />
          )}
          {turn.latencyAsrMs != null && (
            <Latency label="ASR" ms={turn.latencyAsrMs} />
          )}
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3 space-y-2 text-sm">
        {/* User ASR */}
        <div className="flex gap-2">
          <span className="text-xs font-medium text-muted-foreground w-12 shrink-0 pt-0.5">使用者</span>
          <span className="text-foreground break-words">{turn.asr || <span className="text-muted-foreground/50 italic">辨識中…</span>}</span>
        </div>

        {/* Agent sentences — stream in one by one */}
        {turn.sentences.length > 0 && (
          <div className="flex gap-2">
            <span className="text-xs font-medium text-muted-foreground w-12 shrink-0 pt-0.5">Agent</span>
            <div className="space-y-1.5 flex-1 min-w-0">
              {turn.sentences.map((s, i) => (
                <div key={i} className="space-y-0.5">
                  <p className="text-foreground break-words">{s.sentence}</p>
                  {expanded && (
                    <p className="text-xs text-muted-foreground font-mono break-all">{s.taibun}</p>
                  )}
                </div>
              ))}
              {!turn.done && (
                <span className="inline-block w-2 h-4 bg-muted rounded animate-pulse" />
              )}
            </div>
          </div>
        )}

        {/* Expand toggle for taibun */}
        {turn.sentences.length > 0 && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            {expanded ? "▲ 收起台羅" : "▼ 展開台羅拼音"}
          </button>
        )}
      </div>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function Latency({ label, ms }: { label: string; ms: number }) {
  const color =
    ms < 1000 ? "text-green-600 bg-green-500/10" :
    ms < 2000 ? "text-yellow-600 bg-yellow-500/10 dark:text-yellow-400" :
    "text-red-600 bg-red-500/10 dark:text-red-400";
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${color}`}>
      <span className="opacity-70">{label}</span>
      <span className="tabular-nums">{ms.toLocaleString()} ms</span>
    </span>
  );
}

type Color = "green" | "yellow" | "red" | "gray";
const COLOR_CARD: Record<Color, string> = {
  green: "text-green-800",
  yellow: "text-yellow-800",
  red: "text-red-800",
  gray: "text-muted-foreground",
};

function StatCard({ label, value, color }: { label: string; value: string; color: Color }) {
  return (
    <Card className={COLOR_CARD[color]}>
      <CardContent className="pt-4">
        <div className="text-xs font-medium opacity-60 mb-1">{label}</div>
        <div className="text-2xl font-bold tabular-nums">{value}</div>
      </CardContent>
    </Card>
  );
}
