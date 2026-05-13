"use client";

import { useState, useRef } from "react";
import type { PronunciationEntry } from "@taigi-flow/db";
import { Trash2, Pencil, Plus, Download, Upload, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type Agent = { id: string; name: string };

type Props = {
  globalEntries: PronunciationEntry[];
  agents: Agent[];
};

export default function DictionaryManager({ globalEntries, agents }: Props) {
  const [tab, setTab] = useState<string>("global");
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

  async function handleTabChange(t: string) {
    setTab(t);
    if (loadedTabs.has(t)) return;
    const pid = t === "global" ? "global" : t;
    const res = await fetch(`/api/dictionary?profileId=${pid}`);
    const data = await res.json() as { items: PronunciationEntry[] };
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
      const entry = await res.json() as PronunciationEntry;
      setEntries((prev) => ({ ...prev, [tab]: [entry, ...(prev[tab] ?? [])] }));
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
      const updated = await res.json() as PronunciationEntry;
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
        const entry = await res.json() as PronunciationEntry;
        setEntries((prev) => ({ ...prev, [tab]: [entry, ...(prev[tab] ?? [])] }));
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
          <Button variant="outline" size="sm" onClick={exportCsv}>
            <Download size={14} /> 匯出 CSV
          </Button>
          <Button variant="outline" size="sm" disabled={busy} onClick={() => fileRef.current?.click()}>
            <Upload size={14} /> 批次匯入
          </Button>
          <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={importCsv} />
          <Button size="sm" onClick={() => setAdding(true)}>
            <Plus size={14} /> 新增
          </Button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={(v) => void handleTabChange(v ?? "global")} className="mb-4">
        <TabsList variant="line">
          <TabsTrigger value="global">全域</TabsTrigger>
          {agents.map((a) => (
            <TabsTrigger key={a.id} value={a.id}>{a.name}</TabsTrigger>
          ))}
        </TabsList>

        {/* Search — shared across tabs */}
        <div className="mt-3">
          <Input
            type="text"
            placeholder="搜尋詞彙或替換…"
            className="max-w-xs"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* Add row */}
        {adding && (
          <div className="flex gap-2 items-center mt-3 p-3 bg-primary/5 rounded-lg border border-primary/20">
            <Input
              autoFocus
              placeholder="詞彙"
              className="flex-1"
              value={newForm.term}
              onChange={(e) => setNewForm((f) => ({ ...f, term: e.target.value }))}
            />
            <Input
              placeholder="替換"
              className="flex-1"
              value={newForm.replacement}
              onChange={(e) => setNewForm((f) => ({ ...f, replacement: e.target.value }))}
            />
            <Input
              type="number"
              placeholder="優先"
              className="w-20"
              value={newForm.priority}
              onChange={(e) => setNewForm((f) => ({ ...f, priority: e.target.value }))}
            />
            <Input
              placeholder="備註"
              className="flex-1"
              value={newForm.note}
              onChange={(e) => setNewForm((f) => ({ ...f, note: e.target.value }))}
            />
            <Button variant="ghost" size="icon-sm" onClick={() => void saveNew()} disabled={busy}>
              <Check size={16} className="text-green-600" />
            </Button>
            <Button variant="ghost" size="icon-sm" onClick={() => setAdding(false)}>
              <X size={16} />
            </Button>
          </div>
        )}

        <TabsContent value={tab}>
          <div className="rounded-md border mt-3">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>詞彙</TableHead>
                  <TableHead>替換</TableHead>
                  <TableHead className="w-16 text-right">優先</TableHead>
                  <TableHead>備註</TableHead>
                  <TableHead className="w-16" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {visible.map((e) =>
                  editId === e.id ? (
                    <TableRow key={e.id} className="bg-primary/5">
                      <TableCell>
                        <Input
                          value={String(editForm.term ?? "")}
                          onChange={(ev) => setEditForm((f) => ({ ...f, term: ev.target.value }))}
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          value={String(editForm.replacement ?? "")}
                          onChange={(ev) => setEditForm((f) => ({ ...f, replacement: ev.target.value }))}
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          type="number"
                          className="text-right"
                          value={String(editForm.priority ?? 0)}
                          onChange={(ev) =>
                            setEditForm((f) => ({ ...f, priority: parseInt(ev.target.value) || 0 }))
                          }
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          value={String(editForm.note ?? "")}
                          onChange={(ev) => setEditForm((f) => ({ ...f, note: ev.target.value }))}
                        />
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="icon-sm" onClick={() => void saveEdit(e.id)} disabled={busy}>
                            <Check size={14} className="text-green-600" />
                          </Button>
                          <Button variant="ghost" size="icon-sm" onClick={() => setEditId(null)}>
                            <X size={14} />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ) : (
                    <TableRow key={e.id}>
                      <TableCell className="font-medium">{e.term}</TableCell>
                      <TableCell className="text-primary">{e.replacement}</TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {e.priority}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-xs">{e.note ?? ""}</TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => {
                              setEditId(e.id);
                              setEditForm({ term: e.term, replacement: e.replacement, priority: e.priority, note: e.note ?? "" });
                            }}
                          >
                            <Pencil size={14} />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            disabled={busy}
                            onClick={() => void deleteEntry(e.id)}
                            className="text-muted-foreground hover:text-destructive"
                          >
                            <Trash2 size={14} />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ),
                )}
              </TableBody>
            </Table>
            {visible.length === 0 && (
              <p className="text-center text-muted-foreground text-sm py-8">尚無條目</p>
            )}
          </div>
        </TabsContent>
      </Tabs>

      {/* Badge summary */}
      <p className="text-xs text-muted-foreground mt-2">
        共 <Badge variant="secondary">{visible.length}</Badge> 筆
      </p>
    </div>
  );
}

function parseCsvLine(line: string): string[] {
  const result: string[] = [];
  let cur = "";
  let inQuote = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuote && line[i + 1] === '"') { cur += '"'; i++; }
      else inQuote = !inQuote;
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
