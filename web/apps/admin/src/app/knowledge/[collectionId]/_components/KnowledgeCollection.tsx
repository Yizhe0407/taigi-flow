"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  FileText,
  FileType2,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { confirmDialog } from "@/components/confirm-dialog";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

type Chunk = {
  id: string;
  content: string;
  metadata: Record<string, unknown>;
  createdAt: Date | string;
};

type Job = {
  id: string;
  fileName: string;
  filePath: string;
  status: string;
  chunkCount: number;
  error: string | null;
  createdAt: Date | string;
};

type Props = {
  profileName: string;
  collectionId: string;
  initialChunks: Chunk[];
  initialJobs: Job[];
};

function FileIcon({ name, className }: { name: string; className?: string }) {
  const ext = name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return <FileType2 className={className} />;
  return <FileText className={className} />;
}

const STATUS_COLOR: Record<string, string> = {
  pending: "bg-yellow-500/10 text-yellow-600 dark:text-yellow-400",
  processing: "bg-blue-500/10 text-blue-600 dark:text-blue-400",
  done: "bg-green-500/10 text-green-600 dark:text-green-400",
  failed: "bg-red-500/10 text-red-600 dark:text-red-400",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "等待中",
  processing: "處理中",
  done: "完成",
  failed: "失敗",
};

export default function KnowledgeCollection({
  profileName,
  collectionId,
  initialChunks,
  initialJobs,
}: Props) {
  const [chunks, setChunks] = useState<Chunk[]>(initialChunks);
  const [jobs, setJobs] = useState<Job[]>(initialJobs);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [deletingJob, setDeletingJob] = useState<string | null>(null);
  const [deletingChunk, setDeletingChunk] = useState<string | null>(null);
  const [expandedJobs, setExpandedJobs] = useState<Set<string>>(new Set());
  const fileRef = useRef<HTMLInputElement>(null);
  const dropRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    const [chunksRes, jobsRes] = await Promise.all([
      fetch(`/api/knowledge/${collectionId}/chunks`),
      fetch(`/api/knowledge/${collectionId}/jobs`),
    ]);
    if (chunksRes.ok) setChunks(await chunksRes.json());
    if (jobsRes.ok) setJobs(await jobsRes.json());
  }, [collectionId]);

  useEffect(() => {
    const hasActive = jobs.some(
      (j) => j.status === "pending" || j.status === "processing"
    );
    if (!hasActive) return;
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, [jobs, refresh]);

  function toggleExpand(jobId: string) {
    setExpandedJobs((prev) => {
      const next = new Set(prev);
      if (next.has(jobId)) next.delete(jobId);
      else next.add(jobId);
      return next;
    });
  }

  function chunksForJob(job: Job) {
    // Primary: match by jobId stored in metadata (new chunks)
    const byId = chunks.filter((c) => c.metadata.jobId === job.id);
    if (byId.length > 0) return byId;
    // Fallback: match by source = basename of filePath (chunks ingested before jobId field)
    const srcName = job.filePath.split("/").pop() ?? "";
    return srcName ? chunks.filter((c) => c.metadata.source === srcName) : [];
  }

  // Chunks with no matching IngestJob (job record deleted, or ingested before jobId field)
  const knownJobIds = new Set(jobs.map((j) => j.id));
  const knownSources = new Set(jobs.map((j) => j.filePath.split("/").pop() ?? ""));
  const orphanChunks = chunks.filter((c) => {
    if (c.metadata.jobId && knownJobIds.has(c.metadata.jobId as string)) return false;
    if (c.metadata.source && knownSources.has(c.metadata.source as string)) return false;
    return true;
  });

  // Group orphans by source filename
  const orphanGroups = orphanChunks.reduce<Record<string, Chunk[]>>((acc, c) => {
    const src = (c.metadata.source as string | undefined) ?? "未知來源";
    (acc[src] ??= []).push(c);
    return acc;
  }, {});

  function onFileSelect(file: File | undefined) {
    if (!file) return;
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (!["pdf", "md", "txt", "docx"].includes(ext ?? "")) {
      toast.error(`不支援 .${ext ?? "?"} 格式，請上傳 PDF、Markdown、TXT 或 DOCX`);
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      toast.error("檔案超過 20 MB 上限");
      return;
    }
    setSelectedFile(file);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setIsDragging(false);
    onFileSelect(e.dataTransfer.files[0]);
  }

  async function handleUpload() {
    if (!selectedFile) return;
    setUploading(true);
    setUploadProgress(10);
    try {
      const form = new FormData();
      form.append("file", selectedFile);
      setUploadProgress(40);
      const res = await fetch(`/api/knowledge/${collectionId}/upload`, {
        method: "POST",
        body: form,
      });
      setUploadProgress(80);
      if (!res.ok) {
        const d = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(typeof d.error === "string" ? d.error : JSON.stringify(d));
      }
      setUploadProgress(100);
      setSelectedFile(null);
      if (fileRef.current) fileRef.current.value = "";
      toast.success(`「${selectedFile.name}」上傳成功，等待 ingest worker 處理`);
      await refresh();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "上傳失敗");
    } finally {
      setUploading(false);
      setUploadProgress(0);
    }
  }

  async function deleteJob(jobId: string, fileName: string) {
    const ok = await confirmDialog({ description: `確定要刪除「${fileName}」及其所有 chunks 嗎？`, confirmLabel: "刪除" });
    if (!ok) return;
    setDeletingJob(jobId);
    try {
      const res = await fetch(`/api/knowledge/${collectionId}/jobs/${jobId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setJobs((prev) => prev.filter((j) => j.id !== jobId));
        setChunks((prev) => prev.filter((c) => c.metadata.jobId !== jobId));
        setExpandedJobs((prev) => { const s = new Set(prev); s.delete(jobId); return s; });
      }
    } finally {
      setDeletingJob(null);
    }
  }

  async function deleteChunk(chunkId: string) {
    setDeletingChunk(chunkId);
    try {
      const res = await fetch(
        `/api/knowledge/${collectionId}/chunks/${chunkId}`,
        { method: "DELETE" }
      );
      if (res.ok) setChunks((prev) => prev.filter((c) => c.id !== chunkId));
    } finally {
      setDeletingChunk(null);
    }
  }

  async function deleteCollection() {
    const ok = await confirmDialog({ title: "清空知識庫", description: `確定要刪除「${profileName}」知識庫的所有內容嗎？此操作無法復原。`, confirmLabel: "清空" });
    if (!ok) return;
    await fetch(`/api/knowledge/${collectionId}`, { method: "DELETE" });
    setChunks([]);
    setJobs([]);
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{profileName} — 知識庫</h1>
          <p className="text-xs text-muted-foreground mt-0.5">{collectionId}</p>
        </div>
        <Button variant="destructive" size="sm" onClick={deleteCollection}>
          清空知識庫
        </Button>
      </div>

      {/* Upload */}
      <section className="space-y-3">
        <input
          ref={fileRef}
          type="file"
          accept=".pdf,.md,.txt,.docx"
          className="hidden"
          onChange={(e) => onFileSelect(e.target.files?.[0])}
        />

        {/* Dropzone */}
        <div
          ref={dropRef}
          onClick={() => !selectedFile && fileRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={onDrop}
          className={[
            "relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-10 text-center transition-colors",
            isDragging
              ? "border-primary bg-primary/5 scale-[1.01]"
              : selectedFile
                ? "border-primary/40 bg-primary/5"
                : "border-border hover:border-primary/50 hover:bg-muted/30 cursor-pointer",
          ].join(" ")}
        >
          {selectedFile ? (
            <>
              <FileIcon name={selectedFile.name} className="size-12 text-primary" />
              <div>
                <p className="font-medium text-sm">{selectedFile.name}</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {(selectedFile.size / 1024).toFixed(0)} KB
                </p>
              </div>
              <Button
                variant="ghost"
                size="icon-sm"
                className="absolute top-3 right-3 text-muted-foreground hover:text-foreground"
                onClick={(e) => { e.stopPropagation(); setSelectedFile(null); if (fileRef.current) fileRef.current.value = ""; }}
              >
                <X className="size-4" />
              </Button>
            </>
          ) : (
            <>
              <div className="flex size-14 items-center justify-center rounded-full bg-muted">
                <Upload className="size-6 text-muted-foreground" />
              </div>
              <div>
                <p className="font-medium text-sm">拖放文件到這裡，或點擊選取</p>
                <p className="text-xs text-muted-foreground mt-1">
                  支援 PDF、Markdown、TXT、DOCX，最大 20 MB
                </p>
              </div>
            </>
          )}
        </div>

        {/* Upload progress */}
        {uploading && (
          <div className="space-y-1.5">
            <Progress value={uploadProgress} className="h-1.5" />
            <p className="text-xs text-muted-foreground text-center">上傳中…</p>
          </div>
        )}

        {/* Upload button */}
        {selectedFile && !uploading && (
          <Button className="w-full gap-2" onClick={() => void handleUpload()}>
            <Upload className="size-4" />
            上傳「{selectedFile.name}」
          </Button>
        )}
      </section>

      {/* File list */}
      <section className="space-y-2">
        <h2 className="font-semibold">
          已上傳文件（{jobs.length + Object.keys(orphanGroups).length}）
        </h2>

        {jobs.length === 0 && Object.keys(orphanGroups).length === 0 ? (
          <p className="text-sm text-muted-foreground">尚未上傳任何文件。</p>
        ) : (
          <div className="space-y-2">
            {jobs.map((job) => {
              const expanded = expandedJobs.has(job.id);
              const jobChunks = chunksForJob(job);
              const canExpand = job.status === "done" && job.chunkCount > 0;

              return (
                <div key={job.id} className="border border-border rounded-lg bg-card overflow-hidden">
                  {/* Job row */}
                  <div className="flex items-center gap-3 px-4 py-3">
                    {/* Expand toggle */}
                    <button
                      className="text-muted-foreground hover:text-foreground disabled:opacity-30 shrink-0"
                      disabled={!canExpand}
                      onClick={() => toggleExpand(job.id)}
                      aria-label={expanded ? "收合" : "展開"}
                    >
                      {expanded
                        ? <ChevronDown className="w-4 h-4" />
                        : <ChevronRight className="w-4 h-4" />
                      }
                    </button>

                    {/* Status badge */}
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${STATUS_COLOR[job.status] ?? "bg-muted text-muted-foreground"}`}
                    >
                      {STATUS_LABEL[job.status] ?? job.status}
                    </span>

                    {/* Filename */}
                    <span className="font-medium truncate flex-1">{job.fileName}</span>

                    {/* Metadata */}
                    <div className="flex items-center gap-3 text-sm text-muted-foreground shrink-0">
                      {job.status === "done" && (
                        <span>{job.chunkCount} chunks</span>
                      )}
                      {job.error && (
                        <span className="text-red-500 text-xs max-w-xs truncate" title={job.error}>
                          {job.error}
                        </span>
                      )}
                      <span className="text-xs" suppressHydrationWarning>
                        {new Date(job.createdAt).toLocaleString("zh-TW")}
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                        disabled={deletingJob === job.id}
                        onClick={() => deleteJob(job.id, job.fileName)}
                        aria-label="刪除此檔案"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>

                  {/* Chunks (expanded) */}
                  {expanded && (
                    <div className="border-t border-border divide-y divide-border">
                      {jobChunks.map((chunk, i) => (
                        <div key={chunk.id} className="flex items-start gap-3 px-4 py-3 bg-muted/30">
                          <span className="text-xs text-muted-foreground w-6 shrink-0 pt-0.5">#{i + 1}</span>
                          <p className="text-sm text-foreground flex-1 line-clamp-3">
                            {chunk.content.slice(0, 300)}
                            {chunk.content.length > 300 ? "…" : ""}
                          </p>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0 text-muted-foreground/40 hover:text-destructive shrink-0"
                            disabled={deletingChunk === chunk.id}
                            onClick={() => deleteChunk(chunk.id)}
                            aria-label="刪除此 chunk"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
            {/* Orphan chunk groups (job record missing) */}
            {Object.entries(orphanGroups).map(([src, grpChunks]) => {
              const key = `orphan-${src}`;
              const expanded = expandedJobs.has(key);
              return (
                <div key={key} className="border border-dashed border-border rounded-lg bg-card overflow-hidden">
                  <div className="flex items-center gap-3 px-4 py-3">
                    <button
                      className="text-muted-foreground hover:text-foreground shrink-0"
                      onClick={() => toggleExpand(key)}
                      aria-label={expanded ? "收合" : "展開"}
                    >
                      {expanded
                        ? <ChevronDown className="w-4 h-4" />
                        : <ChevronRight className="w-4 h-4" />
                      }
                    </button>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground shrink-0">
                      無紀錄
                    </span>
                    <span className="font-medium truncate flex-1 text-muted-foreground">{src}</span>
                    <span className="text-sm text-muted-foreground shrink-0">{grpChunks.length} chunks</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive shrink-0"
                      onClick={async () => {
                        const ok = await confirmDialog({ description: `確定要刪除「${src}」的所有 chunks 嗎？`, confirmLabel: "刪除" });
                        if (!ok) return;
                        const results = await Promise.all(
                          grpChunks.map((c) =>
                            fetch(`/api/knowledge/${collectionId}/chunks/${c.id}`, {
                              method: "DELETE",
                            })
                          )
                        );
                        const failed = results.filter((r) => !r.ok).length;
                        if (failed > 0) {
                          toast.error(`${failed} 個 chunk 刪除失敗，請重新整理後再試。`);
                        }
                        const succeeded = grpChunks.filter((_, i) => results[i].ok);
                        setChunks((prev) =>
                          prev.filter((c) => !succeeded.some((g) => g.id === c.id))
                        );
                      }}
                      aria-label="刪除此群組所有 chunks"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                  {expanded && (
                    <div className="border-t border-border divide-y divide-border">
                      {grpChunks.map((chunk, i) => (
                        <div key={chunk.id} className="flex items-start gap-3 px-4 py-3 bg-muted/30">
                          <span className="text-xs text-muted-foreground w-6 shrink-0 pt-0.5">#{i + 1}</span>
                          <p className="text-sm text-foreground flex-1 line-clamp-3">
                            {chunk.content.slice(0, 300)}
                            {chunk.content.length > 300 ? "…" : ""}
                          </p>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0 text-muted-foreground/40 hover:text-destructive shrink-0"
                            disabled={deletingChunk === chunk.id}
                            onClick={() => deleteChunk(chunk.id)}
                            aria-label="刪除此 chunk"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}
