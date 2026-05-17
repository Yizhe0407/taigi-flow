"use client";

import { useRouter } from "next/navigation";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { confirmDialog } from "@/components/confirm-dialog";

type Item = {
  id: string;
  name: string;
  ragEnabled: boolean;
  chunkCount: number;
};

export default function KnowledgeList({ items }: { items: Item[] }) {
  const router = useRouter();

  async function deleteCollection(e: React.MouseEvent, item: Item) {
    e.stopPropagation();
    const ok = await confirmDialog({
      title: "清空知識庫",
      description: `確定要刪除「${item.name}」知識庫的所有內容嗎？此操作無法復原。`,
      confirmLabel: "清空",
    });
    if (!ok) return;
    const res = await fetch(`/api/knowledge/${item.id}`, { method: "DELETE" });
    if (res.ok) {
      toast.success(`已清空「${item.name}」知識庫`);
      router.refresh();
    } else {
      toast.error("清空失敗");
    }
  }

  if (items.length === 0) {
    return (
      <p className="text-muted-foreground text-sm py-8 text-center">
        尚無 Agent 人格。請先在「Agent 人格」頁面建立。
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div
          key={item.id}
          className="flex items-center justify-between border border-border rounded-lg px-4 py-3 bg-card hover:bg-accent/30 cursor-pointer transition-colors"
          onClick={() => router.push(`/knowledge/${item.id}`)}
        >
          <div>
            <div className="font-medium">{item.name}</div>
            <div className="text-xs text-muted-foreground mt-0.5">{item.id}</div>
          </div>

          <div className="flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
            <span className="text-sm text-muted-foreground">{item.chunkCount} chunks</span>
            <span
              className={`text-xs px-2 py-0.5 rounded-full ${
                item.ragEnabled
                  ? "bg-green-500/10 text-green-600 dark:text-green-400"
                  : "bg-muted text-muted-foreground"
              }`}
            >
              {item.ragEnabled ? "RAG 啟用" : "RAG 停用"}
            </span>
            <Button
              variant="ghost"
              size="icon-sm"
              title="清空知識庫"
              className="text-muted-foreground hover:text-destructive"
              onClick={(e) => void deleteCollection(e, item)}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        </div>
      ))}
    </div>
  );
}
