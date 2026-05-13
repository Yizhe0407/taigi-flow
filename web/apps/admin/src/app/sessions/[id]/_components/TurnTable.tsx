"use client";

import { useState } from "react";
import type { InteractionLog } from "@taigi-flow/db";

type Filter = { bargedIn: boolean; hasError: boolean; minLatency: string };

export default function TurnTable({ turns }: { turns: InteractionLog[] }) {
  const [filter, setFilter] = useState<Filter>({
    bargedIn: false,
    hasError: false,
    minLatency: "",
  });

  const filtered = turns.filter((t) => {
    if (filter.bargedIn && !t.wasBargedIn) return false;
    if (filter.hasError && !t.errorFlag) return false;
    const minMs = parseInt(filter.minLatency);
    if (!isNaN(minMs) && (t.latencyTotal ?? 0) < minMs) return false;
    return true;
  });

  return (
    <div>
      {/* Filters */}
      <div className="flex items-center gap-4 mb-4 text-sm">
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={filter.bargedIn}
            onChange={(e) =>
              setFilter((f) => ({ ...f, bargedIn: e.target.checked }))
            }
          />
          被打斷
        </label>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input
            type="checkbox"
            checked={filter.hasError}
            onChange={(e) =>
              setFilter((f) => ({ ...f, hasError: e.target.checked }))
            }
          />
          有錯誤
        </label>
        <label className="flex items-center gap-1.5">
          延遲 ≥
          <input
            type="number"
            placeholder="ms"
            className="w-20 px-2 py-0.5 border border-gray-300 rounded text-sm"
            value={filter.minLatency}
            onChange={(e) =>
              setFilter((f) => ({ ...f, minLatency: e.target.value }))
            }
          />
          ms
        </label>
        <span className="text-gray-400 text-xs">
          {filtered.length} / {turns.length} 輪
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-200">
              <th className="py-2 pr-3 font-medium w-8">#</th>
              <th className="py-2 pr-3 font-medium w-1/4">ASR 辨識</th>
              <th className="py-2 pr-3 font-medium w-1/4">LLM 回應</th>
              <th className="py-2 pr-3 font-medium w-1/4">HanLo 文字</th>
              <th className="py-2 pr-3 font-medium w-1/4">Taibun 注音</th>
              <th className="py-2 pr-3 font-medium whitespace-nowrap">首音(ms)</th>
              <th className="py-2 pr-3 font-medium whitespace-nowrap">總計(ms)</th>
              <th className="py-2 font-medium">標記</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t) => (
              <tr
                key={t.id}
                className={`border-b border-gray-100 align-top ${
                  t.wasBargedIn ? "bg-amber-50" : ""
                } ${t.errorFlag ? "bg-red-50" : ""}`}
              >
                <td className="py-2 pr-3 text-gray-400">{t.turnIndex}</td>
                <td className="py-2 pr-3 break-words">{t.userAsrText}</td>
                <td className="py-2 pr-3 break-words">{t.llmRawText}</td>
                <td className="py-2 pr-3 break-words">{t.hanloText ?? "—"}</td>
                <td className="py-2 pr-3 break-words font-mono">{t.taibunText}</td>
                <td className="py-2 pr-3 tabular-nums">
                  {t.latencyFirstAudio ?? "—"}
                </td>
                <td className="py-2 pr-3 tabular-nums">
                  {t.latencyTotal ?? "—"}
                </td>
                <td className="py-2 space-y-0.5">
                  {t.wasBargedIn && (
                    <span className="block px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded text-xs leading-none">
                      打斷
                    </span>
                  )}
                  {t.errorFlag && (
                    <span
                      title={t.errorFlag}
                      className="block px-1.5 py-0.5 bg-red-100 text-red-700 rounded text-xs leading-none cursor-help"
                    >
                      錯誤
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <p className="text-center text-gray-400 text-sm py-8">無符合條件的紀錄</p>
        )}
      </div>
    </div>
  );
}
