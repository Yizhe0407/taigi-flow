"use client";

import { useEffect, useRef, useState } from "react";
import type { InteractionLog } from "@taigi-flow/db";

type TurnWithProfile = InteractionLog & {
  session: { agentProfile: { name: string } };
};

type Stats = {
  activeSessions: number;
  avgFirstAudioMs: number | null;
  errorRate: number;
};

const MAX_FEED = 100;

export default function MonitorDashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [turns, setTurns] = useState<TurnWithProfile[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const es = new EventSource("/api/monitor/stream");
    esRef.current = es;

    es.addEventListener("snapshot", (e) => {
      const data = JSON.parse(e.data) as TurnWithProfile[];
      setTurns(data.reverse()); // newest first
      setConnected(true);
    });

    es.addEventListener("turn", (e) => {
      const turn = JSON.parse(e.data) as TurnWithProfile;
      setTurns((prev) => [turn, ...prev].slice(0, MAX_FEED));
    });

    es.addEventListener("stats", (e) => {
      setStats(JSON.parse(e.data) as Stats);
    });

    es.addEventListener("error", (e) => {
      if ("data" in e) {
        try { setError((JSON.parse((e as MessageEvent).data) as { message: string }).message); }
        catch { /* ignore */ }
      }
      setConnected(false);
    });

    es.onopen = () => { setConnected(true); setError(null); };
    es.onerror = () => setConnected(false);

    return () => {
      es.close();
    };
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">即時監控</h1>
        <div className="flex items-center gap-2 text-sm">
          <span
            className={`inline-block w-2 h-2 rounded-full ${
              connected ? "bg-green-500 animate-pulse" : "bg-red-400"
            }`}
          />
          <span className="text-gray-500">{connected ? "串流連線中" : "未連線"}</span>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <Metric
          label="進行中 Session"
          value={stats ? String(stats.activeSessions) : "—"}
          color={stats?.activeSessions ? "green" : "gray"}
        />
        <Metric
          label="最近 100 輪首音延遲"
          value={stats?.avgFirstAudioMs != null ? `${stats.avgFirstAudioMs} ms` : "—"}
          color={
            stats?.avgFirstAudioMs == null
              ? "gray"
              : stats.avgFirstAudioMs < 1500
                ? "green"
                : stats.avgFirstAudioMs < 3000
                  ? "yellow"
                  : "red"
          }
        />
        <Metric
          label="錯誤率（近 100 輪）"
          value={stats ? `${stats.errorRate}%` : "—"}
          color={
            !stats ? "gray" : stats.errorRate === 0 ? "green" : stats.errorRate < 5 ? "yellow" : "red"
          }
        />
      </div>

      {/* Live turn feed */}
      <div>
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          對話串流
        </h2>

        {turns.length === 0 && (
          <p className="text-gray-400 text-sm py-8 text-center">
            等待對話…
          </p>
        )}

        <div className="space-y-2">
          {turns.map((t) => (
            <TurnCard key={t.id} turn={t} />
          ))}
        </div>
      </div>
    </div>
  );
}

function TurnCard({ turn }: { turn: TurnWithProfile }) {
  const ts = new Date(turn.createdAt).toLocaleTimeString("zh-TW", {
    timeZone: "Asia/Taipei",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <div
      className={`p-3 rounded-lg border text-sm ${
        turn.wasBargedIn
          ? "border-amber-200 bg-amber-50"
          : turn.errorFlag
            ? "border-red-200 bg-red-50"
            : "border-gray-100 bg-white"
      }`}
    >
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400 tabular-nums">{ts}</span>
          <span className="text-xs text-gray-400">·</span>
          <span className="text-xs font-medium text-gray-600">
            {turn.session.agentProfile.name}
          </span>
          <span className="text-xs text-gray-400">·</span>
          <span className="text-xs text-gray-400">Turn {turn.turnIndex}</span>
        </div>
        <div className="flex items-center gap-2 text-xs tabular-nums">
          {turn.latencyFirstAudio != null && (
            <LatencyBadge label="首音" ms={turn.latencyFirstAudio} />
          )}
          {turn.latencyLlmFirstTok != null && (
            <LatencyBadge label="LLM" ms={turn.latencyLlmFirstTok} />
          )}
          {turn.wasBargedIn && (
            <span className="px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded leading-none">
              打斷
            </span>
          )}
          {turn.errorFlag && (
            <span
              title={turn.errorFlag}
              className="px-1.5 py-0.5 bg-red-100 text-red-700 rounded leading-none cursor-help"
            >
              錯誤
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <Row label="ASR" text={turn.userAsrText} />
        <Row label="LLM" text={turn.llmRawText} />
        {turn.hanloText && <Row label="漢羅" text={turn.hanloText} />}
        <Row label="台羅" text={turn.taibunText} mono />
      </div>
    </div>
  );
}

function Row({ label, text, mono = false }: { label: string; text: string; mono?: boolean }) {
  return (
    <div className="flex gap-1.5 min-w-0">
      <span className="text-gray-400 shrink-0 w-8">{label}</span>
      <span className={`text-gray-700 truncate ${mono ? "font-mono" : ""}`}>{text}</span>
    </div>
  );
}

function LatencyBadge({ label, ms }: { label: string; ms: number }) {
  const color =
    ms < 1000 ? "text-green-600" : ms < 2000 ? "text-yellow-600" : "text-red-600";
  return (
    <span className={`${color} font-medium`}>
      {label} {ms}ms
    </span>
  );
}

type Color = "green" | "yellow" | "red" | "gray";
const COLOR_MAP: Record<Color, string> = {
  green: "border-green-200 bg-green-50 text-green-700",
  yellow: "border-yellow-200 bg-yellow-50 text-yellow-700",
  red: "border-red-200 bg-red-50 text-red-700",
  gray: "border-gray-200 bg-white text-gray-700",
};

function Metric({ label, value, color }: { label: string; value: string; color: Color }) {
  return (
    <div className={`p-5 border rounded-lg ${COLOR_MAP[color]}`}>
      <div className="text-xs font-medium mb-2 opacity-70">{label}</div>
      <div className="text-3xl font-bold tabular-nums">{value}</div>
    </div>
  );
}
