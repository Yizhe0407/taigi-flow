"use client";

import { useState, useRef } from "react";
import type { PronunciationEntry } from "@taigi-flow/db";
import { Check, Download, MoreHorizontal, Pencil, Plus, Trash2, Upload, X } from "lucide-react";
import { toast } from "sonner";
import { confirmDialog } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PageHeader } from "@/components/page-header";

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

  async function errorMessage(res: Response, fallback: string) {
    const data = await res.json().catch(() => null);
    if (data && typeof data.error === "string") return data.error;
    return `${fallback} (${res.status})`;
  }

  async function handleTabChange(t: string) {
    setTab(t);
    if (loadedTabs.has(t)) return;
    try {
      const pid = t === "global" ? "global" : t;
      const res = await fetch(`/api/dictionary?profileId=${pid}`);
      if (!res.ok) throw new Error(await errorMessage(res, "載入字典失敗"));
      const data = await res.json() as { items: PronunciationEntry[] };
      setEntries((prev) => ({ ...prev, [t]: data.items }));
      setLoadedTabs((prev) => new Set(prev).add(t));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "載入字典失敗");
    }
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
      if (!res.ok) throw new Error(await errorMessage(res, "新增失敗"));
      const entry = await res.json() as PronunciationEntry;
      if (res.status === 201) {
        setEntries((prev) => ({ ...prev, [tab]: [entry, ...(prev[tab] ?? [])] }));
      } else {
        setEntries((prev) => ({
          ...prev,
          [tab]: (prev[tab] ?? []).some((e) => e.id === entry.id)
            ? (prev[tab] ?? []).map((e) => (e.id === entry.id ? entry : e))
            : [entry, ...(prev[tab] ?? [])],
        }));
      }
      setAdding(false);
      setNewForm({ term: "", replacement: "", priority: "0", note: "" });
      toast.success("已新增字典條目");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "新增失敗");
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
      if (!res.ok) throw new Error(await errorMessage(res, "更新失敗"));
      const updated = await res.json() as PronunciationEntry;
      setEntries((prev) => ({
        ...prev,
        [tab]: (prev[tab] ?? []).map((e) => (e.id === updated.id ? updated : e)),
      }));
      setEditId(null);
      toast.success("已更新字典條目");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "更新失敗");
    } finally {
      setBusy(false);
    }
  }

  async function deleteEntry(id: string) {
    const ok = await confirmDialog({ description: "確定要刪除此條目？", confirmLabel: "刪除" });
    if (!ok) return;
    setBusy(true);
    try {
      const res = await fetch(`/api/dictionary/${id}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await errorMessage(res, "刪除失敗"));
      setEntries((prev) => ({
        ...prev,
        [tab]: (prev[tab] ?? []).filter((e) => e.id !== id),
      }));
      toast.success("已刪除字典條目");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "刪除失敗");
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
    setBusy(true);
    let imported = 0;
    let failed = 0;
    try {
      const text = await file.text();
      const rows = parseCsv(text).slice(1).filter((r) => r.some(Boolean));
      for (const cols of rows) {
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
          if (res.status === 201) {
            setEntries((prev) => ({ ...prev, [tab]: [entry, ...(prev[tab] ?? [])] }));
          } else {
            setEntries((prev) => ({
              ...prev,
              [tab]: (prev[tab] ?? []).some((e) => e.id === entry.id)
                ? (prev[tab] ?? []).map((e) => (e.id === entry.id ? entry : e))
                : [entry, ...(prev[tab] ?? [])],
            }));
          }
          imported++;
        } else {
          failed++;
        }
      }
      if (failed > 0) {
        toast.error(`匯入完成：${imported} 筆，失敗 ${failed} 筆`);
      } else {
        toast.success(`匯入完成：${imported} 筆`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "匯入失敗");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <div>
      <input ref={fileRef} type="file" accept=".csv" className="hidden" onChange={importCsv} />
      <PageHeader
        title="發音字典"
        description="設定台語詞彙的自訂發音替換規則"
        action={
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={exportCsv}>
              <Download className="size-3.5" /> 匯出 CSV
            </Button>
            <Button variant="outline" size="sm" disabled={busy} onClick={() => fileRef.current?.click()}>
              <Upload className="size-3.5" /> 批次匯入
            </Button>
            <Button size="sm" onClick={() => setAdding(true)}>
              <Plus className="size-3.5" /> 新增
            </Button>
          </div>
        }
      />

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
                        <DropdownMenu>
                          <DropdownMenuTrigger
                            render={<Button variant="ghost" size="icon-sm" />}
                          >
                            <MoreHorizontal className="size-4" />
                            <span className="sr-only">操作</span>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => {
                                setEditId(e.id);
                                setEditForm({ term: e.term, replacement: e.replacement, priority: e.priority, note: e.note ?? "" });
                              }}
                            >
                              <Pencil className="size-3.5 mr-2" /> 編輯
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="text-destructive"
                              disabled={busy}
                              onClick={() => void deleteEntry(e.id)}
                            >
                              <Trash2 className="size-3.5 mr-2" /> 刪除
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
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

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let cur = "";
  let inQuote = false;
  let row: string[] = [];
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === '"') {
      if (inQuote && text[i + 1] === '"') { cur += '"'; i++; }
      else inQuote = !inQuote;
    } else if (ch === "," && !inQuote) {
      row.push(cur); cur = "";
    } else if (ch === "\r" && text[i + 1] === "\n" && !inQuote) {
      i++;
      row.push(cur); cur = "";
      rows.push(row); row = [];
    } else if (ch === "\n" && !inQuote) {
      row.push(cur); cur = "";
      rows.push(row); row = [];
    } else {
      cur += ch;
    }
  }
  if (cur || row.length > 0) { row.push(cur); rows.push(row); }
  return rows;
}
