"use client";

import { useState, useRef } from "react";
import type { PronunciationEntry } from "@taigi-flow/db";
import { Trash2, Pencil, Plus, Download, Upload, Check, X } from "lucide-react";

type Agent = { id: string; name: string };

type Props = {
  globalEntries: PronunciationEntry[];
  agents: Agent[];
};

type Tab = "global" | string; // profileId or "global"

export default function DictionaryManager({ globalEntries, agents }: Props) {
  const [tab, setTab] = useState<Tab>("global");
  const [entries, setEntries] = useState<Record<string, PronunciationEntry[]>>({
    global: globalEntries,
  });
  const [loadedTabs, setLoadedTabs] = useState<Set<string>>(new Set(["global"]));
  const [search, setSearch] = useState("");
  const [editId, setEditId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<PronunciationEntry>>({});
  const [adding, setAdding] = useState(false);
  const [newForm, setNewForm] = useState({ term: "", replacement: "", priority: "0", note: "" });
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const profileId = tab === "global" ? null : tab;
  const tabEntries = entries[tab] ?? [];
  const visible = tabEntries.filter((e) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return e.term.toLowerCase().includes(q) || e.replacement.toLowerCase().includes(q);
  });

  async function loadTab(t: Tab) {
    setTab(t);
    if (loadedTabs.has(t)) return;
    const pid = t === "global" ? "global" : t;
    const res = await fetch(`/api/dictionary?profileId=${pid}`);
    const data = await res.json();
    setEntries((prev) => ({ ...prev, [t]: data.items }));
    setLoadedTabs((prev) => new Set(prev).add(t));
  }

  async function saveNew() {
    if (!newForm.term || !newForm.replacement) return;
    setBusy(true);
    try {
      const res = await fetch("/api/dictionary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profileId,
          term: newForm.term,
          replacement: newForm.replacement,
          priority: parseInt(newForm.priority) || 0,
          note: newForm.note || null,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const entry: PronunciationEntry = await res.json();
      setEntries((prev) => ({
        ...prev,
        [tab]: [entry, ...(prev[tab] ?? [])],
      }));
      setAdding(false);
      setNewForm({ term: "", replacement: "", priority: "0", note: "" });
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(id: string) {
    setBusy(true);
    try {
      const res = await fetch(`/api/dictionary/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          term: editForm.term,
          replacement: editForm.replacement,
          priority: editForm.priority,
          note: editForm.note || null,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const updated: PronunciationEntry = await res.json();
      setEntries((prev) => ({
        ...prev,
        [tab]: (prev[tab] ?? []).map((e) => (e.id === updated.id ? updated : e)),
      }));
      setEditId(null);
    } finally {
      setBusy(false);
    }
  }

  async function deleteEntry(id: string) {
    if (!confirm("刪除此條目？")) return;
    setBusy(true);
    try {
      const res = await fetch(`/api/dictionary/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      setEntries((prev) => ({
        ...prev,
        [tab]: (prev[tab] ?? []).filter((e) => e.id !== id),
      }));
    } finally {
      setBusy(false);
    }
  }

  function exportCsv() {
    const header = "term,replacement,priority,note";
    const rows = tabEntries.map(
      (e) =>
        `"${e.term.replace(/"/g, '""')}","${e.replacement.replace(/"/g, '""')}",${e.priority},"${(e.note ?? "").replace(/"/g, '""')}"`,
    );
    const blob = new Blob([[header, ...rows].join("\n")], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `dictionary-${tab}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function importCsv(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    const lines = text.split(/\r?\n/).slice(1).filter(Boolean);
    setBusy(true);
    let imported = 0;
    for (const line of lines) {
      const cols = parseCsvLine(line);
      if (!cols[0] || !cols[1]) continue;
      const res = await fetch("/api/dictionary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profileId,
          term: cols[0],
          replacement: cols[1],
          priority: parseInt(cols[2] ?? "0") || 0,
          note: cols[3] || null,
        }),
      });
      if (res.ok) {
        const entry: PronunciationEntry = await res.json();
        setEntries((prev) => ({
          ...prev,
          [tab]: [entry, ...(prev[tab] ?? [])],
        }));
        imported++;
      }
    }
    setBusy(false);
    alert(`匯入完成：${imported} 筆`);
    if (fileRef.current) fileRef.current.value = "";
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-2xl font-bold">發音字典</h1>
        <div className="flex gap-2">
          <button
            onClick={exportCsv}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50"
          >
            <Download size={14} /> 匯出 CSV
          </button>
          <button
            onClick={() => fileRef.current?.click()}
            disabled={busy}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-sm border border-gray-300 rounded hover:bg-gray-50 disabled:opacity-50"
          >
            <Upload size={14} /> 批次匯入
          </button>
          <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={importCsv} />
          <button
            onClick={() => setAdding(true)}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-sm bg-indigo-600 text-white rounded hover:bg-indigo-700"
          >
            <Plus size={14} /> 新增
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 mb-4 border-b border-gray-200">
        <TabBtn active={tab === "global"} onClick={() => loadTab("global")}>
          全域
        </TabBtn>
        {agents.map((a) => (
          <TabBtn key={a.id} active={tab === a.id} onClick={() => loadTab(a.id)}>
            {a.name}
          </TabBtn>
        ))}
      </div>

      {/* Search */}
      <input
        type="text"
        placeholder="搜尋詞彙或替換…"
        className="input max-w-xs mb-4"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {/* Add row */}
      {adding && (
        <div className="flex gap-2 items-center mb-3 p-3 bg-indigo-50 rounded">
          <input
            autoFocus
            placeholder="詞彙"
            className="input flex-1"
            value={newForm.term}
            onChange={(e) => setNewForm((f) => ({ ...f, term: e.target.value }))}
          />
          <input
            placeholder="替換"
            className="input flex-1"
            value={newForm.replacement}
            onChange={(e) => setNewForm((f) => ({ ...f, replacement: e.target.value }))}
          />
          <input
            type="number"
            placeholder="優先"
            className="input w-20"
            value={newForm.priority}
            onChange={(e) => setNewForm((f) => ({ ...f, priority: e.target.value }))}
          />
          <input
            placeholder="備註"
            className="input flex-1"
            value={newForm.note}
            onChange={(e) => setNewForm((f) => ({ ...f, note: e.target.value }))}
          />
          <button onClick={saveNew} disabled={busy} className="text-green-600 hover:text-green-800 disabled:opacity-40">
            <Check size={18} />
          </button>
          <button onClick={() => setAdding(false)} className="text-gray-400 hover:text-gray-600">
            <X size={18} />
          </button>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-xs text-gray-500 border-b border-gray-200">
              <th className="py-2 pr-3 font-medium">詞彙</th>
              <th className="py-2 pr-3 font-medium">替換</th>
              <th className="py-2 pr-3 font-medium w-16 text-right">優先</th>
              <th className="py-2 pr-3 font-medium">備註</th>
              <th className="py-2 w-16" />
            </tr>
          </thead>
          <tbody>
            {visible.map((e) =>
              editId === e.id ? (
                <tr key={e.id} className="border-b border-indigo-100 bg-indigo-50">
                  <td className="py-1.5 pr-3">
                    <input
                      className="input"
                      value={String(editForm.term ?? "")}
                      onChange={(ev) => setEditForm((f) => ({ ...f, term: ev.target.value }))}
                    />
                  </td>
                  <td className="py-1.5 pr-3">
                    <input
                      className="input"
                      value={String(editForm.replacement ?? "")}
                      onChange={(ev) =>
                        setEditForm((f) => ({ ...f, replacement: ev.target.value }))
                      }
                    />
                  </td>
                  <td className="py-1.5 pr-3">
                    <input
                      type="number"
                      className="input text-right"
                      value={String(editForm.priority ?? 0)}
                      onChange={(ev) =>
                        setEditForm((f) => ({ ...f, priority: parseInt(ev.target.value) || 0 }))
                      }
                    />
                  </td>
                  <td className="py-1.5 pr-3">
                    <input
                      className="input"
                      value={String(editForm.note ?? "")}
                      onChange={(ev) => setEditForm((f) => ({ ...f, note: ev.target.value }))}
                    />
                  </td>
                  <td className="py-1.5 flex gap-1">
                    <button
                      onClick={() => saveEdit(e.id)}
                      disabled={busy}
                      className="text-green-600 hover:text-green-800 disabled:opacity-40"
                    >
                      <Check size={16} />
                    </button>
                    <button onClick={() => setEditId(null)} className="text-gray-400 hover:text-gray-600">
                      <X size={16} />
                    </button>
                  </td>
                </tr>
              ) : (
                <tr key={e.id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="py-2 pr-3 font-medium">{e.term}</td>
                  <td className="py-2 pr-3 text-indigo-700">{e.replacement}</td>
                  <td className="py-2 pr-3 text-right tabular-nums text-gray-500">
                    {e.priority}
                  </td>
                  <td className="py-2 pr-3 text-gray-400 text-xs">{e.note ?? ""}</td>
                  <td className="py-2 flex gap-2">
                    <button
                      onClick={() => {
                        setEditId(e.id);
                        setEditForm({ term: e.term, replacement: e.replacement, priority: e.priority, note: e.note ?? "" });
                      }}
                      className="text-gray-400 hover:text-blue-600"
                    >
                      <Pencil size={15} />
                    </button>
                    <button
                      onClick={() => deleteEntry(e.id)}
                      disabled={busy}
                      className="text-gray-400 hover:text-red-500 disabled:opacity-40"
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                </tr>
              ),
            )}
          </tbody>
        </table>
        {visible.length === 0 && (
          <p className="text-center text-gray-400 text-sm py-8">尚無條目</p>
        )}
      </div>
    </div>
  );
}

function TabBtn({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
        active
          ? "border-indigo-600 text-indigo-600"
          : "border-transparent text-gray-500 hover:text-gray-700"
      }`}
    >
      {children}
    </button>
  );
}

function parseCsvLine(line: string): string[] {
  const result: string[] = [];
  let cur = "";
  let inQuote = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuote && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else {
        inQuote = !inQuote;
      }
    } else if (ch === "," && !inQuote) {
      result.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  result.push(cur);
  return result;
}
