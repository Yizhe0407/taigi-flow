"use client";

import { useEffect, useState, useCallback } from "react";
import { RefreshCw } from "lucide-react";

type Stats = {
  activeSessions: number;
  recentTurns: number;
  avgFirstAudioMs: number | null;
  errorRate: number;
};

const POLL_MS = 10_000;

export default function MonitorDashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/monitor");
      if (!res.ok) throw new Error(await res.text());
      setStats(await res.json());
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "fetch failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
    const id = setInterval(fetchStats, POLL_MS);
    return () => clearInterval(id);
  }, [fetchStats]);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">即時監控</h1>
        <div className="flex items-center gap-3 text-sm text-gray-500">
          {lastUpdated && (
            <span>
              更新於 {lastUpdated.toLocaleTimeString("zh-TW")}（每 {POLL_MS / 1000}s 輪詢）
            </span>
          )}
          <button
            onClick={fetchStats}
            disabled={loading}
            className="inline-flex items-center gap-1 px-3 py-1.5 border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-40"
          >
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} /> 刷新
          </button>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
          {error}
        </div>
      )}

      {!stats && !error && (
        <div className="text-gray-400 text-sm">載入中…</div>
      )}

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Metric
            label="進行中 Session"
            value={String(stats.activeSessions)}
            color={stats.activeSessions > 0 ? "green" : "gray"}
          />
          <Metric
            label="最近 100 輪首音延遲"
            value={
              stats.avgFirstAudioMs !== null
                ? `${stats.avgFirstAudioMs} ms`
                : "—"
            }
            color={
              stats.avgFirstAudioMs === null
                ? "gray"
                : stats.avgFirstAudioMs < 1500
                  ? "green"
                  : stats.avgFirstAudioMs < 3000
                    ? "yellow"
                    : "red"
            }
          />
          <Metric
            label="最近 100 輪錯誤率"
            value={`${stats.errorRate}%`}
            color={stats.errorRate === 0 ? "green" : stats.errorRate < 5 ? "yellow" : "red"}
          />
          <Metric
            label="取樣輪次數"
            value={String(stats.recentTurns)}
            color="gray"
          />
        </div>
      )}
    </div>
  );
}

type Color = "green" | "yellow" | "red" | "gray";

const COLOR_MAP: Record<Color, string> = {
  green: "border-green-200 bg-green-50 text-green-700",
  yellow: "border-yellow-200 bg-yellow-50 text-yellow-700",
  red: "border-red-200 bg-red-50 text-red-700",
  gray: "border-gray-200 bg-white text-gray-700",
};

function Metric({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: Color;
}) {
  return (
    <div className={`p-5 border rounded-lg ${COLOR_MAP[color]}`}>
      <div className="text-xs font-medium mb-2 opacity-70">{label}</div>
      <div className="text-3xl font-bold tabular-nums">{value}</div>
    </div>
  );
}
