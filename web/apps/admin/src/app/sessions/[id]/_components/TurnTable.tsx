"use client";

import { useState } from "react";
import type { InteractionLog } from "@taigi-flow/db";
import { BookPlus, Check, X } from "lucide-react";

export type TurnView = Pick<
  InteractionLog,
  | "id"
  | "turnIndex"
  | "userAsrText"
  | "llmRawText"
  | "hanloText"
  | "taibunText"
  | "latencyFirstAudio"
  | "latencyTotal"
  | "wasBargedIn"
  | "errorFlag"
>;
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

type Filter = { bargedIn: boolean; hasError: boolean; minLatency: string };

type AddDictState = { logId: string; term: string; replacement: string };

export default function TurnTable({ turns }: { turns: TurnView[] }) {
  const [filter, setFilter] = useState<Filter>({ bargedIn: false, hasError: false, minLatency: "" });
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
        body: JSON.stringify({ logId: addDict.logId, term: addDict.term, replacement: addDict.replacement }),
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
      <div className="flex items-center gap-4 mb-4 text-sm flex-wrap">
        <label className="flex items-center gap-1.5 cursor-pointer">
          <Checkbox
            checked={filter.bargedIn}
            onCheckedChange={(v) => setFilter((f) => ({ ...f, bargedIn: v }))}
          />
          被打斷
        </label>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <Checkbox
            checked={filter.hasError}
            onCheckedChange={(v) => setFilter((f) => ({ ...f, hasError: v }))}
          />
          有錯誤
        </label>
        <div className="flex items-center gap-1.5">
          <span>延遲 ≥</span>
          <Input
            type="number"
            placeholder="ms"
            className="w-20 h-7"
            value={filter.minLatency}
            onChange={(e) => setFilter((f) => ({ ...f, minLatency: e.target.value }))}
          />
          <span>ms</span>
        </div>
        <Badge variant="secondary">
          {filtered.length} / {turns.length} 輪
        </Badge>
      </div>

      {/* Table */}
      <div className="rounded-md border overflow-x-auto">
        <Table className="text-xs">
          <TableHeader>
            <TableRow>
              <TableHead className="w-8">#</TableHead>
              <TableHead className="w-1/4">ASR 辨識</TableHead>
              <TableHead className="w-1/4">LLM 回應</TableHead>
              <TableHead className="w-1/4">HanLo 文字</TableHead>
              <TableHead className="w-1/4">Taibun 注音</TableHead>
              <TableHead className="whitespace-nowrap">首音(ms)</TableHead>
              <TableHead className="whitespace-nowrap">總計(ms)</TableHead>
              <TableHead>標記</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((t) => (
              <TableRow
                key={t.id}
                className={`align-top ${t.wasBargedIn ? "bg-amber-50" : ""} ${t.errorFlag ? "bg-red-50" : ""}`}
              >
                <TableCell className="text-muted-foreground">{t.turnIndex}</TableCell>
                <TableCell className="break-words">{t.userAsrText}</TableCell>
                <TableCell className="break-words">{t.llmRawText}</TableCell>
                <TableCell className="break-words">{t.hanloText ?? "—"}</TableCell>
                <TableCell className="break-words font-mono">{t.taibunText}</TableCell>
                <TableCell className="tabular-nums">{t.latencyFirstAudio ?? "—"}</TableCell>
                <TableCell className="tabular-nums">{t.latencyTotal ?? "—"}</TableCell>
                <TableCell>
                  <div className="space-y-0.5">
                    {t.wasBargedIn && <Badge variant="outline" className="text-amber-600 border-amber-300 text-xs">打斷</Badge>}
                    {t.errorFlag && (
                      <Badge variant="outline" className="text-destructive border-destructive/30 text-xs cursor-help" title={t.errorFlag}>
                        錯誤
                      </Badge>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    title="加入字典"
                    onClick={() => setAddDict({ logId: t.id, term: t.userAsrText, replacement: "" })}
                    className="text-muted-foreground hover:text-primary"
                  >
                    <BookPlus size={14} />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {filtered.length === 0 && (
          <p className="text-center text-muted-foreground text-sm py-8">無符合條件的紀錄</p>
        )}
      </div>

      {/* Add-to-dict dialog */}
      <Dialog open={!!addDict} onOpenChange={(open) => { if (!open) setAddDict(null); }}>
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>加入發音字典</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="dict-term">詞彙</Label>
              <Input
                id="dict-term"
                value={addDict?.term ?? ""}
                onChange={(e) => setAddDict((s) => s && { ...s, term: e.target.value })}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="dict-replacement">替換（台羅拼音）</Label>
              <Input
                id="dict-replacement"
                autoFocus
                placeholder="e.g. Tâi-uân"
                value={addDict?.replacement ?? ""}
                onChange={(e) => setAddDict((s) => s && { ...s, replacement: e.target.value })}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              onClick={() => void submitAddDict()}
              disabled={addBusy || !addDict?.replacement}
            >
              <Check size={14} /> 確認加入
            </Button>
            <Button variant="outline" onClick={() => setAddDict(null)}>
              <X size={14} /> 取消
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
