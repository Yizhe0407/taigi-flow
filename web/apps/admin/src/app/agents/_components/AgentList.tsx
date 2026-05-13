"use client";

import { useState } from "react";
import Link from "next/link";
import type { AgentProfile } from "@taigi-flow/db";
import { PencilLine, Trash2, Plus, Radio } from "lucide-react";

export default function AgentList({ initial }: { initial: AgentProfile[] }) {
  const [profiles, setProfiles] = useState(initial);
  const [busy, setBusy] = useState<string | null>(null);

  async function activate(p: AgentProfile) {
    if (p.isActive) return; // already active
    setBusy(p.id);
    try {
      const res = await fetch(`/api/agent-profiles/${p.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ isActive: true }),
      });
      if (!res.ok) throw new Error(await res.text());
      // Server deactivated all others — reflect locally
      setProfiles((prev) => prev.map((x) => ({ ...x, isActive: x.id === p.id })));
    } finally {
      setBusy(null);
    }
  }

  async function deleteProfile(p: AgentProfile) {
    if (!confirm(`刪除「${p.name}」？此操作無法復原。`)) return;
    setBusy(p.id);
    try {
      const res = await fetch(`/api/agent-profiles/${p.id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      setProfiles((prev) => prev.filter((x) => x.id !== p.id));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Agent 人格管理</h1>
        <Link
          href="/agents/new"
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white text-sm rounded hover:bg-indigo-700"
        >
          <Plus size={16} /> 新增人格
        </Link>
      </div>

      <p className="text-xs text-gray-400 mb-4">同一時間只能啟用一個人格。點選未啟用的人格即可切換。</p>

      {profiles.length === 0 && (
        <p className="text-gray-500 text-sm">尚無 Agent 人格，請新增一個。</p>
      )}

      <div className="space-y-2">
        {profiles.map((p) => (
          <div
            key={p.id}
            className={`flex items-center gap-4 p-4 rounded-lg border transition-colors ${
              p.isActive
                ? "border-indigo-300 bg-indigo-50"
                : "border-gray-200 bg-white opacity-70 hover:opacity-90 cursor-pointer"
            }`}
            onClick={() => !p.isActive && !busy && activate(p)}
          >
            {/* Radio indicator */}
            <button
              title={p.isActive ? "目前啟用中" : "點擊啟用"}
              disabled={p.isActive || busy === p.id}
              onClick={(e) => { e.stopPropagation(); activate(p); }}
              className="shrink-0 disabled:cursor-default"
            >
              <Radio
                size={20}
                className={p.isActive ? "text-indigo-600" : "text-gray-300"}
              />
            </button>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium">{p.name}</span>
                {p.isActive && (
                  <span className="text-xs px-1.5 py-0.5 bg-indigo-100 text-indigo-700 rounded">
                    使用中
                  </span>
                )}
              </div>
              {p.description && (
                <p className="text-sm text-gray-500 mt-0.5 truncate">{p.description}</p>
              )}
            </div>

            <div className="flex items-center gap-2 shrink-0" onClick={(e) => e.stopPropagation()}>
              <Link
                href={`/agents/${p.id}`}
                className="text-gray-400 hover:text-blue-600"
                title="編輯"
              >
                <PencilLine size={18} />
              </Link>
              <button
                title="刪除"
                disabled={busy === p.id}
                onClick={() => deleteProfile(p)}
                className="text-gray-400 hover:text-red-500 disabled:opacity-40"
              >
                <Trash2 size={18} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
