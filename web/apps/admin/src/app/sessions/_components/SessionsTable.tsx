"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowDown, ArrowUp, ArrowUpDown, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { confirmDialog } from "@/components/confirm-dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

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
    <Badge variant="outline" className="text-amber-500 border-amber-300" title="Worker 未正常結束">
      未正常結束
    </Badge>
  );
}

function SortHeader({
  label, col, sortBy, sortDir, onSort,
}: {
  label: string;
  col: SortBy;
  sortBy: SortBy;
  sortDir: SortDir;
  onSort: (col: SortBy) => void;
}) {
  const Icon =
    col !== sortBy ? ArrowUpDown :
    sortDir === "asc" ? ArrowUp : ArrowDown;
  return (
    <Button
      variant="ghost"
      size="sm"
      className="-ml-3 h-8 gap-1 font-medium"
      onClick={() => onSort(col)}
    >
      {label}
      <Icon className="size-3.5 text-muted-foreground" />
    </Button>
  );
}

export default function SessionsTable({ agents }: { agents: AgentOption[] }) {
  const router = useRouter();
  const [rows, setRows] = useState<SessionRow[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [deleting, setDeleting] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [agentFilter, setAgentFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortBy, setSortBy] = useState<SortBy>("startedAt");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const fetchSessions = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ sortBy, sortDir, limit: "200" });
      if (agentFilter !== "all") params.set("agentProfileId", agentFilter);
      if (statusFilter !== "all") params.set("status", statusFilter);
      const res = await fetch(`/api/sessions?${params}`);
      if (!res.ok) throw new Error(await errorMessage(res, "載入對話紀錄失敗"));
      const data = await res.json() as { items: SessionRow[]; nextCursor: string | null };
      setRows(data.items);
      setNextCursor(data.nextCursor);
      setSelected(new Set());
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "載入對話紀錄失敗");
    } finally {
      setLoading(false);
    }
  }, [agentFilter, statusFilter, sortBy, sortDir]);

  useEffect(() => { void fetchSessions(); }, [fetchSessions]);

  const loadMore = useCallback(async () => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const params = new URLSearchParams({ sortBy, sortDir, limit: "200", cursor: nextCursor });
      if (agentFilter !== "all") params.set("agentProfileId", agentFilter);
      if (statusFilter !== "all") params.set("status", statusFilter);
      const res = await fetch(`/api/sessions?${params}`);
      if (!res.ok) throw new Error(await errorMessage(res, "載入更多失敗"));
      const data = await res.json() as { items: SessionRow[]; nextCursor: string | null };
      setRows((prev) => [...prev, ...data.items]);
      setNextCursor(data.nextCursor);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "載入更多失敗");
    } finally {
      setLoadingMore(false);
    }
  }, [nextCursor, loadingMore, sortBy, sortDir, agentFilter, statusFilter]);

  function toggleSort(col: SortBy) {
    if (sortBy === col) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortBy(col); setSortDir("desc"); }
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

  async function deleteRow(id: string) {
    const ok = await confirmDialog({ description: "確定要刪除此對話紀錄？此操作無法復原。", confirmLabel: "刪除" });
    if (!ok) return;
    setDeletingId(id);
    try {
      const res = await fetch("/api/sessions", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: [id] }),
      });
      if (!res.ok) throw new Error(await errorMessage(res, "刪除失敗"));
      setRows((prev) => prev.filter((r) => r.id !== id));
      setSelected((prev) => {
        const s = new Set(prev);
        s.delete(id);
        return s;
      });
      toast.success("已刪除");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "刪除失敗");
    } finally {
      setDeletingId(null);
    }
  }

  async function deleteSelected() {
    const ok = await confirmDialog({
      description: `確定要刪除 ${selected.size} 筆對話紀錄？此操作無法復原。`,
      confirmLabel: "刪除",
    });
    if (!ok) return;
    const ids = Array.from(selected);
    const idSet = new Set(ids);
    setDeleting(true);
    try {
      const res = await fetch("/api/sessions", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids }),
      });
      if (!res.ok) throw new Error(await errorMessage(res, "批次刪除失敗"));
      setRows((prev) => prev.filter((row) => !idSet.has(row.id)));
      setSelected(new Set());
      toast.success(`已刪除 ${ids.length} 筆`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "批次刪除失敗");
    } finally {
      setDeleting(false);
    }
  }

  const allSelected = rows.length > 0 && selected.size === rows.length;
  const someSelected = selected.size > 0 && !allSelected;

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <NativeSelect value={statusFilter} onChange={(v) => setStatusFilter(v as StatusFilter)} className="w-36">
          <option value="all">所有狀態</option>
          <option value="active">進行中</option>
          <option value="ended">已結束</option>
          <option value="stale">未正常結束</option>
        </NativeSelect>

        <NativeSelect value={agentFilter} onChange={setAgentFilter} className="w-44">
          <option value="all">所有 Role</option>
          {agents.map((a) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </NativeSelect>

        {selected.size > 0 && (
          <Button
            variant="destructive"
            size="sm"
            disabled={deleting}
            onClick={() => void deleteSelected()}
            className="ml-auto gap-1.5"
          >
            <Trash2 className="size-3.5" />
            刪除 {selected.size} 筆
          </Button>
        )}
      </div>

      {/* Table */}
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">
                <Checkbox
                  checked={allSelected}
                  indeterminate={someSelected}
                  onCheckedChange={(v) => toggleAll(!!v)}
                />
              </TableHead>
              <TableHead>
                <SortHeader label="時間" col="startedAt" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} />
              </TableHead>
              <TableHead>Agent</TableHead>
              <TableHead>房間</TableHead>
              <TableHead>
                <SortHeader label="輪次" col="turnCount" sortBy={sortBy} sortDir={sortDir} onSort={toggleSort} />
              </TableHead>
              <TableHead>狀態</TableHead>
              <TableHead className="w-12" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <TableRow key={i}>
                  {Array.from({ length: 7 }).map((__, j) => (
                    <TableCell key={j}><Skeleton className="h-4 w-full" /></TableCell>
                  ))}
                </TableRow>
              ))
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                  無符合條件的紀錄
                </TableCell>
              </TableRow>
            ) : rows.map((row) => {
              const status = sessionStatus(row);
              return (
                <TableRow
                  key={row.id}
                  data-state={selected.has(row.id) ? "selected" : undefined}
                  className="cursor-pointer"
                  onClick={() => router.push(`/sessions/${row.id}`)}
                >
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Checkbox
                      checked={selected.has(row.id)}
                      onCheckedChange={(v) => toggleRow(row.id, !!v)}
                    />
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground" suppressHydrationWarning>
                    {new Date(row.startedAt).toLocaleString("zh-TW", { timeZone: "Asia/Taipei" })}
                  </TableCell>
                  <TableCell className="font-medium">{row.agentProfile.name}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground max-w-[160px] truncate">
                    {row.livekitRoom}
                  </TableCell>
                  <TableCell>{row._count.logs}</TableCell>
                  <TableCell><StatusBadge status={status} /></TableCell>
                  <TableCell onClick={(e) => e.stopPropagation()}>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      title="刪除"
                      disabled={deleting || deletingId === row.id}
                      className="text-muted-foreground hover:text-destructive"
                      onClick={() => void deleteRow(row.id)}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>

      {!loading && rows.length > 0 && (
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span>{rows.length} 筆紀錄</span>
          {nextCursor && (
            <Button
              variant="outline"
              size="sm"
              disabled={loadingMore}
              onClick={() => void loadMore()}
            >
              {loadingMore ? "載入中…" : "載入更多"}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

async function errorMessage(res: Response, fallback: string) {
  const data = await res.json().catch(() => null);
  if (data && typeof data.error === "string") return data.error;
  return `${fallback} (${res.status})`;
}

function NativeSelect({
  value,
  onChange,
  className,
  children,
}: {
  value: string;
  onChange: (v: string) => void;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cn(
        "h-8 rounded-lg border border-input bg-background px-2.5 text-sm",
        "focus-visible:outline-none focus:ring-2 focus:ring-ring",
        "cursor-pointer text-foreground",
        className,
      )}
    >
      {children}
    </select>
  );
}
