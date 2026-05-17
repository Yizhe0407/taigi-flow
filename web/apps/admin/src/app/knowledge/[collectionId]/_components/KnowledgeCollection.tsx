"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Trash2 } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

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

const STATUS_COLOR: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-700",
  processing: "bg-blue-100 text-blue-700",
  done: "bg-green-100 text-green-700",
  failed: "bg-red-100 text-red-700",
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
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [deletingJob, setDeletingJob] = useState<string | null>(null);
  const [deletingChunk, setDeletingChunk] = useState<string | null>(null);
  const [expandedJobs, setExpandedJobs] = useState<Set<string>>(new Set());
  const fileRef = useRef<HTMLInputElement>(null);

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

  async function handleUpload(e: React.FormEvent) {
    e.preventDefault();
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`/api/knowledge/${collectionId}/upload`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({ error: res.statusText }));
        throw new Error(typeof d.error === "string" ? d.error : JSON.stringify(d));
      }
      if (fileRef.current) fileRef.current.value = "";
      await refresh();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : String(err));
    } finally {
      setUploading(false);
    }
  }

  async function deleteJob(jobId: string, fileName: string) {
    if (!confirm(`確定要刪除「${fileName}」及其所有 chunks 嗎？`)) return;
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
    if (!confirm(`確定要刪除「${profileName}」知識庫的所有內容嗎？`)) return;
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
          <p className="text-xs text-gray-400 mt-0.5">{collectionId}</p>
        </div>
        <Button variant="destructive" size="sm" onClick={deleteCollection}>
          清空知識庫
        </Button>
      </div>

      {/* Upload */}
      <section className="border border-border rounded-lg p-5 space-y-3">
        <h2 className="font-semibold">上傳文件</h2>
        <p className="text-sm text-gray-500">支援 PDF、Markdown、TXT、DOCX，最大 20 MB。</p>
        {uploadError && (
          <Alert variant="destructive">
            <AlertDescription>{uploadError}</AlertDescription>
          </Alert>
        )}
        <form onSubmit={handleUpload} className="flex gap-3 items-center">
          <input
            ref={fileRef}
            type="file"
            accept=".pdf,.md,.txt,.docx"
            className="flex-1 text-sm border border-border rounded px-3 py-1.5 bg-white"
          />
          <Button type="submit" disabled={uploading}>
            {uploading ? "上傳中…" : "上傳"}
          </Button>
        </form>
      </section>

      {/* File list */}
      <section className="space-y-2">
        <h2 className="font-semibold">
          已上傳文件（{jobs.length + Object.keys(orphanGroups).length}）
        </h2>

        {jobs.length === 0 && Object.keys(orphanGroups).length === 0 ? (
          <p className="text-sm text-gray-400">尚未上傳任何文件。</p>
        ) : (
          <div className="space-y-2">
            {jobs.map((job) => {
              const expanded = expandedJobs.has(job.id);
              const jobChunks = chunksForJob(job);
              const canExpand = job.status === "done" && job.chunkCount > 0;

              return (
                <div key={job.id} className="border border-border rounded-lg bg-white overflow-hidden">
                  {/* Job row */}
                  <div className="flex items-center gap-3 px-4 py-3">
                    {/* Expand toggle */}
                    <button
                      className="text-gray-400 hover:text-gray-700 disabled:opacity-30 shrink-0"
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
                      className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${STATUS_COLOR[job.status] ?? "bg-gray-100 text-gray-600"}`}
                    >
                      {STATUS_LABEL[job.status] ?? job.status}
                    </span>

                    {/* Filename */}
                    <span className="font-medium truncate flex-1">{job.fileName}</span>

                    {/* Metadata */}
                    <div className="flex items-center gap-3 text-sm text-gray-400 shrink-0">
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
                        className="h-7 w-7 p-0 text-gray-400 hover:text-red-500"
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
                        <div key={chunk.id} className="flex items-start gap-3 px-4 py-3 bg-gray-50">
                          <span className="text-xs text-gray-400 w-6 shrink-0 pt-0.5">#{i + 1}</span>
                          <p className="text-sm text-gray-700 flex-1 line-clamp-3">
                            {chunk.content.slice(0, 300)}
                            {chunk.content.length > 300 ? "…" : ""}
                          </p>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0 text-gray-300 hover:text-red-500 shrink-0"
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
                <div key={key} className="border border-dashed border-border rounded-lg bg-white overflow-hidden">
                  <div className="flex items-center gap-3 px-4 py-3">
                    <button
                      className="text-gray-400 hover:text-gray-700 shrink-0"
                      onClick={() => toggleExpand(key)}
                      aria-label={expanded ? "收合" : "展開"}
                    >
                      {expanded
                        ? <ChevronDown className="w-4 h-4" />
                        : <ChevronRight className="w-4 h-4" />
                      }
                    </button>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-500 shrink-0">
                      無紀錄
                    </span>
                    <span className="font-medium truncate flex-1 text-gray-500">{src}</span>
                    <span className="text-sm text-gray-400 shrink-0">{grpChunks.length} chunks</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 text-gray-400 hover:text-red-500 shrink-0"
                      onClick={async () => {
                        if (!confirm(`確定要刪除「${src}」的所有 chunks 嗎？`)) return;
                        const results = await Promise.all(
                          grpChunks.map((c) =>
                            fetch(`/api/knowledge/${collectionId}/chunks/${c.id}`, {
                              method: "DELETE",
                            })
                          )
                        );
                        const failed = results.filter((r) => !r.ok).length;
                        if (failed > 0) {
                          alert(`${failed} 個 chunk 刪除失敗，請重新整理後再試。`);
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
                        <div key={chunk.id} className="flex items-start gap-3 px-4 py-3 bg-gray-50">
                          <span className="text-xs text-gray-400 w-6 shrink-0 pt-0.5">#{i + 1}</span>
                          <p className="text-sm text-gray-700 flex-1 line-clamp-3">
                            {chunk.content.slice(0, 300)}
                            {chunk.content.length > 300 ? "…" : ""}
                          </p>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0 text-gray-300 hover:text-red-500 shrink-0"
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
