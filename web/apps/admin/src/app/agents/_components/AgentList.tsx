"use client";

import { useState } from "react";
import Link from "next/link";
import type { AgentProfile } from "@taigi-flow/db";
import { PencilLine, Trash2, Plus, Radio } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function AgentList({ initial }: { initial: AgentProfile[] }) {
  const [profiles, setProfiles] = useState(initial);
  const [busy, setBusy] = useState<string | null>(null);

  async function activate(p: AgentProfile) {
    if (p.isActive) return;
    setBusy(p.id);
    try {
      const res = await fetch(`/api/agent-profiles/${p.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ isActive: true }),
      });
      if (!res.ok) throw new Error(await res.text());
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
        <Link href="/agents/new" className={cn(buttonVariants(), "gap-1.5")}>
          <Plus size={16} /> 新增人格
        </Link>
      </div>

      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-4">
        <span>同一時間只能啟用一個人格。</span>
        <span>·</span>
        <span>切換後，<strong>下次使用者重新連線</strong>時自動套用新人格（不須重啟腳本）。</span>
      </div>

      {profiles.length === 0 && (
        <p className="text-muted-foreground text-sm">尚無 Agent 人格，請新增一個。</p>
      )}

      <div className="space-y-2">
        {profiles.map((p) => (
          <div
            key={p.id}
            className={cn(
              "flex items-center gap-4 p-4 rounded-lg border transition-colors",
              p.isActive
                ? "border-primary/40 bg-primary/5"
                : "border-border bg-card opacity-70 hover:opacity-90 cursor-pointer",
            )}
            onClick={() => !p.isActive && !busy && activate(p)}
          >
            <Button
              title={p.isActive ? "目前啟用中" : "點擊啟用"}
              disabled={p.isActive || busy === p.id}
              variant="ghost"
              size="icon-sm"
              onClick={(e) => { e.stopPropagation(); void activate(p); }}
              className="shrink-0"
            >
              <Radio size={20} className={p.isActive ? "text-primary" : "text-muted-foreground"} />
            </Button>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-medium">{p.name}</span>
                {p.isActive && <Badge variant="secondary">使用中</Badge>}
              </div>
              {p.description && (
                <p className="text-sm text-muted-foreground mt-0.5 truncate">{p.description}</p>
              )}
            </div>

            <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
              <Link
                href={`/agents/${p.id}`}
                title="編輯"
                className={cn(buttonVariants({ variant: "ghost", size: "icon-sm" }))}
              >
                <PencilLine size={16} />
              </Link>
              <Button
                variant="ghost"
                size="icon-sm"
                title="刪除"
                disabled={busy === p.id}
                onClick={() => void deleteProfile(p)}
                className="text-muted-foreground hover:text-destructive"
              >
                <Trash2 size={16} />
              </Button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
