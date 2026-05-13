"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { ArrowUpDown, ArrowUp, ArrowDown, Trash2 } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type AgentOption = { id: string; name: string };

type SessionRow = {
  id: string;
  startedAt: string;
  endedAt: string | null;
  livekitRoom: string;
  agentProfile: { id: string; name: string };
  _count: { logs: number };
};

type SortBy = "startedAt" | "turnCount";
type SortDir = "asc" | "desc";
type StatusFilter = "all" | "active" | "ended" | "stale";

const STALE_MS = 2 * 60 * 60 * 1000;

function sessionStatus(s: SessionRow): "active" | "ended" | "stale" {
  if (s.endedAt) return "ended";
  const age = Date.now() - new Date(s.startedAt).getTime();
  return age > STALE_MS ? "stale" : "active";
}

function StatusBadge({ status }: { status: "active" | "ended" | "stale" }) {
  if (status === "active")
    return <Badge variant="outline" className="text-green-600 border-green-300">進行中</Badge>;
  if (status === "ended")
    return <Badge variant="outline" className="text-gray-400 border-gray-200">已結束</Badge>;
  return (
    <Badge variant="outline" className="text-amber-500 border-amber-300" title="Worker 未正常結束（SIGKILL / 崩潰）">
      未正常結束
    </Badge>
  );
}

function SortIcon({ col, sortBy, sortDir }: { col: SortBy; sortBy: SortBy; sortDir: SortDir }) {
  if (col !== sortBy) return <ArrowUpDown size={14} className="text-gray-400" />;
  return sortDir === "asc"
    ? <ArrowUp size={14} className="text-indigo-600" />
    : <ArrowDown size={14} className="text-indigo-600" />;
}

export default function SessionsTable({ agents }: { agents: AgentOption[] }) {
  const [rows, setRows] = useState<SessionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);

  const [agentFilter, setAgentFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortBy, setSortBy] = useState<SortBy>("startedAt");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({ sortBy, sortDir, limit: "200" });
    if (agentFilter !== "all") params.set("agentProfileId", agentFilter);
    if (statusFilter !== "all") params.set("status", statusFilter);
    const res = await fetch(`/api/sessions?${params}`);
    if (res.ok) {
      const data = await res.json() as { items: SessionRow[] };
      setRows(data.items);
      setSelected(new Set());
    }
    setLoading(false);
  }, [agentFilter, statusFilter, sortBy, sortDir]);

  useEffect(() => { void fetchSessions(); }, [fetchSessions]);

  function toggleSort(col: SortBy) {
    if (sortBy === col) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortBy(col);
      setSortDir("desc");
    }
  }

  function toggleAll(checked: boolean) {
    setSelected(checked ? new Set(rows.map((r) => r.id)) : new Set());
  }

  function toggleRow(id: string, checked: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
  }

  async function deleteSelected() {
    if (selected.size === 0) return;
    if (!confirm(`刪除 ${selected.size} 筆對話紀錄？此操作無法復原。`)) return;
    setDeleting(true);
    try {
      const res = await fetch("/api/sessions", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: Array.from(selected) }),
      });
      if (!res.ok) throw new Error(await res.text());
      await fetchSessions();
    } finally {
      setDeleting(false);
    }
  }

  const allSelected = rows.length > 0 && selected.size === rows.length;
  const someSelected = selected.size > 0 && !allSelected;

  return (
    <div>
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        <Select value={statusFilter} onValueChange={(v) => setStatusFilter((v ?? "all") as StatusFilter)}>
          <SelectTrigger className="w-36">
            <SelectValue placeholder="所有狀態" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">所有狀態</SelectItem>
            <SelectItem value="active">進行中</SelectItem>
            <SelectItem value="ended">已結束</SelectItem>
            <SelectItem value="stale">未正常結束</SelectItem>
          </SelectContent>
        </Select>

        <Select value={agentFilter} onValueChange={(v) => setAgentFilter(v ?? "all")}>
          <SelectTrigger className="w-44">
            <SelectValue placeholder="所有 Agent" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">所有 Agent</SelectItem>
            {agents.map((a) => (
              <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        {selected.size > 0 && (
          <Button
            variant="destructive"
            size="sm"
            disabled={deleting}
            onClick={() => void deleteSelected()}
            className="ml-auto gap-1.5"
          >
            <Trash2 size={14} />
            刪除 {selected.size} 筆
          </Button>
        )}
      </div>

      {loading ? (
        <p className="text-sm text-gray-400 py-8 text-center">載入中…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-gray-500 py-8 text-center">無符合條件的紀錄。</p>
      ) : (
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-10">
                  <Checkbox
                    checked={allSelected}
                    indeterminate={someSelected}
                    onCheckedChange={(v) => toggleAll(v)}
                  />
                </TableHead>
                <TableHead>
                  <button
                    className="flex items-center gap-1 font-medium hover:text-indigo-600"
                    onClick={() => toggleSort("startedAt")}
                  >
                    時間 <SortIcon col="startedAt" sortBy={sortBy} sortDir={sortDir} />
                  </button>
                </TableHead>
                <TableHead>Agent</TableHead>
                <TableHead>房間</TableHead>
                <TableHead>
                  <button
                    className="flex items-center gap-1 font-medium hover:text-indigo-600"
                    onClick={() => toggleSort("turnCount")}
                  >
                    輪次 <SortIcon col="turnCount" sortBy={sortBy} sortDir={sortDir} />
                  </button>
                </TableHead>
                <TableHead>狀態</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => {
                const status = sessionStatus(row);
                return (
                  <TableRow key={row.id} data-state={selected.has(row.id) ? "selected" : undefined}>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <Checkbox
                        checked={selected.has(row.id)}
                        onCheckedChange={(v) => toggleRow(row.id, v)}
                      />
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-gray-600 text-xs">
                      {new Date(row.startedAt).toLocaleString("zh-TW", { timeZone: "Asia/Taipei" })}
                    </TableCell>
                    <TableCell>{row.agentProfile.name}</TableCell>
                    <TableCell className="font-mono text-xs text-gray-500 max-w-[160px] truncate">
                      {row.livekitRoom}
                    </TableCell>
                    <TableCell>{row._count.logs}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <StatusBadge status={status} />
                        <Link
                          href={`/sessions/${row.id}`}
                          className="text-xs text-indigo-600 hover:underline"
                        >
                          查看
                        </Link>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
