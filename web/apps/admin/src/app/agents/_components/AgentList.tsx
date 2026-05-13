"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { AgentProfile } from "@taigi-flow/db";
import { PencilLine, Trash2, ToggleLeft, ToggleRight, Plus } from "lucide-react";

export default function AgentList({ initial }: { initial: AgentProfile[] }) {
  const router = useRouter();
  const [profiles, setProfiles] = useState(initial);
  const [busy, setBusy] = useState<string | null>(null);

  async function toggleActive(p: AgentProfile) {
    setBusy(p.id);
    try {
      const res = await fetch(`/api/agent-profiles/${p.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ isActive: !p.isActive }),
      });
      if (!res.ok) throw new Error(await res.text());
      const updated: AgentProfile = await res.json();
      setProfiles((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
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

      {profiles.length === 0 && (
        <p className="text-gray-500 text-sm">尚無 Agent 人格，請新增一個。</p>
      )}

      <div className="space-y-3">
        {profiles.map((p) => (
          <div
            key={p.id}
            className={`flex items-center gap-4 p-4 bg-white rounded-lg border ${
              p.isActive ? "border-gray-200" : "border-gray-100 opacity-60"
            }`}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium">{p.name}</span>
                {p.isActive ? (
                  <span className="text-xs px-1.5 py-0.5 bg-green-100 text-green-700 rounded">
                    啟用
                  </span>
                ) : (
                  <span className="text-xs px-1.5 py-0.5 bg-gray-100 text-gray-500 rounded">
                    停用
                  </span>
                )}
              </div>
              {p.description && (
                <p className="text-sm text-gray-500 mt-0.5 truncate">{p.description}</p>
              )}
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <button
                title={p.isActive ? "停用" : "啟用"}
                disabled={busy === p.id}
                onClick={() => toggleActive(p)}
                className="text-gray-400 hover:text-indigo-600 disabled:opacity-40"
              >
                {p.isActive ? <ToggleRight size={22} /> : <ToggleLeft size={22} />}
              </button>
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
