"use client";

import { useState } from "react";
import type { InteractionLog } from "@taigi-flow/db";
import { BookPlus, X, Check } from "lucide-react";

type Filter = { bargedIn: boolean; hasError: boolean; minLatency: string };

type AddDictState = {
  logId: string;
  term: string;
  replacement: string;
};

export default function TurnTable({ turns }: { turns: InteractionLog[] }) {
  const [filter, setFilter] = useState<Filter>({
    bargedIn: false,
    hasError: false,
    minLatency: "",
  });

  const [addDict, setAddDict] = useState<AddDictState | null>(null);
  const [addBusy, setAddBusy] = useState(false);

  const filtered = turns.filter((t) => {
    if (filter.bargedIn && !t.wasBargedIn) return false;
    if (filter.hasError && !t.errorFlag) return false;
    const minMs = parseInt(filter.minLatency);
    if (!isNaN(minMs) && (t.latencyTotal ?? 0) < minMs) return false;
    return true;
  });

  async function submitAddDict() {
    if (!addDict) return;
    setAddBusy(true);
    try {
      const res = await fetch("/api/dictionary/from-log", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          logId: addDict.logId,
          term: addDict.term,
          replacement: addDict.replacement,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      setAddDict(null);
      alert("已加入字典");
    } catch (err) {
      alert(err instanceof Error ? err.message : "失敗");
    } finally {
      setAddBusy(false);
    }
  }

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
              <th className="py-2 pr-3 font-medium">標記</th>
              <th className="py-2 font-medium" />
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
                <td className="py-2 pr-3 space-y-0.5">
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
                <td className="py-2">
                  <button
                    title="加入字典"
                    onClick={() =>
                      setAddDict({ logId: t.id, term: t.userAsrText, replacement: "" })
                    }
                    className="text-gray-300 hover:text-indigo-500"
                  >
                    <BookPlus size={14} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <p className="text-center text-gray-400 text-sm py-8">無符合條件的紀錄</p>
        )}
      </div>

      {/* Add-to-dict modal */}
      {addDict && (
        <div className="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg p-6 w-full max-w-md shadow-xl">
            <h2 className="text-base font-semibold mb-4">加入發音字典</h2>
            <div className="space-y-3 text-sm">
              <label className="block">
                <span className="text-gray-600">詞彙</span>
                <input
                  className="input mt-1"
                  value={addDict.term}
                  onChange={(e) =>
                    setAddDict((s) => s && { ...s, term: e.target.value })
                  }
                />
              </label>
              <label className="block">
                <span className="text-gray-600">替換（台羅拼音）</span>
                <input
                  autoFocus
                  className="input mt-1"
                  placeholder="e.g. Tâi-uân"
                  value={addDict.replacement}
                  onChange={(e) =>
                    setAddDict((s) => s && { ...s, replacement: e.target.value })
                  }
                />
              </label>
            </div>
            <div className="flex gap-2 mt-5">
              <button
                onClick={submitAddDict}
                disabled={addBusy || !addDict.replacement}
                className="flex-1 inline-flex items-center justify-center gap-1 py-2 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-700 disabled:opacity-50"
              >
                <Check size={14} /> 確認加入
              </button>
              <button
                onClick={() => setAddDict(null)}
                className="px-4 py-2 border border-gray-300 text-sm rounded hover:bg-gray-50"
              >
                <X size={14} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
