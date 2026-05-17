"use client";

import Link from "next/link";
import { startTransition, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  ChevronDown,
  ChevronRight,
  Database,
  FileText,
  FileType2,
  LoaderCircle,
  Search,
  Settings2,
  Trash2,
  TriangleAlert,
  Upload,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { confirmDialog } from "@/components/confirm-dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

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

type RagConfig = {
  enabled: boolean;
  topK: number;
  threshold: number;
  collectionId: string;
} | null;

type QueryHit = {
  id: string;
  content: string;
  metadata: Record<string, unknown>;
  similarity: number;
  passedThreshold: boolean;
  createdAt: string | null;
};

type QueryResult = {
  collectionId: string;
  query: string;
  topK: number;
  threshold: number;
  metrics: {
    hitCount: number;
    topSimilarity: number;
    latencyMs: number;
    embeddingMs: number;
    dbMs: number;
  };
  results: QueryHit[];
};

type Props = {
  profileName: string;
  collectionId: string;
  ragConfig: RagConfig;
  initialChunks: Chunk[];
  initialChunksHasMore: boolean;
  initialJobs: Job[];
};

function MetricCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <Card size="sm" className="gap-2">
      <CardHeader className="pb-0">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl">{value}</CardTitle>
      </CardHeader>
      <CardContent className="pt-0 text-xs text-muted-foreground">{hint}</CardContent>
    </Card>
  );
}

function FileIcon({ name, className }: { name: string; className?: string }) {
  const ext = name.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return <FileType2 className={className} />;
  return <FileText className={className} />;
}

function sourceFromMetadata(metadata: Record<string, unknown>) {
  return typeof metadata.source === "string" ? metadata.source : "未知來源";
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
  ragConfig,
  initialChunks,
  initialChunksHasMore,
  initialJobs,
}: Props) {
  const router = useRouter();
  const [chunks, setChunks] = useState<Chunk[]>(initialChunks);
  const [chunksHasMore, setChunksHasMore] = useState(initialChunksHasMore);
  const [jobs, setJobs] = useState<Job[]>(initialJobs);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [clearingCollection, setClearingCollection] = useState(false);
  const [deletingJob, setDeletingJob] = useState<string | null>(null);
  const [deletingChunk, setDeletingChunk] = useState<string | null>(null);
  const [expandedJobs, setExpandedJobs] = useState<Set<string>>(new Set());
  const [queryText, setQueryText] = useState("");
  const [queryTopK, setQueryTopK] = useState(String(ragConfig?.topK ?? 3));
  const [queryThreshold, setQueryThreshold] = useState(
    String(ragConfig?.threshold ?? 0.7)
  );
  const [querying, setQuerying] = useState(false);
  const [queryError, setQueryError] = useState<string | null>(null);
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const dropRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    const [chunksRes, jobsRes] = await Promise.all([
      fetch(`/api/knowledge/${collectionId}/chunks`, { cache: "no-store" }),
      fetch(`/api/knowledge/${collectionId}/jobs`, { cache: "no-store" }),
    ]);
    if (chunksRes.ok) {
      const data = await chunksRes.json() as { items: Chunk[]; hasMore: boolean };
      setChunks(data.items);
      setChunksHasMore(data.hasMore);
    }
    if (jobsRes.ok) setJobs(await jobsRes.json());
  }, [collectionId]);

  const syncAfterMutation = useCallback(async () => {
    await refresh();
    startTransition(() => router.refresh());
  }, [refresh, router]);

  const resetCollectionState = useCallback(() => {
    setChunks([]);
    setJobs([]);
    setExpandedJobs(new Set());
    setQueryError(null);
    setQueryResult(null);
  }, []);

  useEffect(() => {
    setChunks(initialChunks);
    setChunksHasMore(initialChunksHasMore);
  }, [initialChunks, initialChunksHasMore]);

  useEffect(() => {
    setJobs(initialJobs);
  }, [initialJobs]);

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
  const orphanEntries = Object.entries(orphanGroups);
  const ragEnabled = ragConfig?.enabled ?? false;
  const indexedJobs = jobs.filter((job) => job.status === "done").length;
  const activeJobs = jobs.filter(
    (job) => job.status === "pending" || job.status === "processing"
  ).length;
  const failedJobs = jobs.filter((job) => job.status === "failed");
  const totalDocuments = jobs.length + orphanEntries.length;
  const collectionMatchesRole =
    ragConfig?.collectionId ? ragConfig.collectionId === collectionId : true;

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
      await syncAfterMutation();
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
      if (!res.ok) {
        const data = await res.json().catch(() => ({ error: "刪除失敗" }));
        throw new Error(typeof data.error === "string" ? data.error : "刪除失敗");
      }
      setExpandedJobs((prev) => {
        const next = new Set(prev);
        next.delete(jobId);
        return next;
      });
      await syncAfterMutation();
      toast.success(`已刪除「${fileName}」`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "刪除失敗");
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
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(
          data && typeof data.error === "string" ? data.error : "刪除 chunk 失敗"
        );
      }

      await syncAfterMutation();
      if (data?.jobDeleted) {
        setExpandedJobs((prev) => {
          const next = new Set(prev);
          if (typeof data.jobId === "string") next.delete(data.jobId);
          return next;
        });
        toast.success("已刪除最後一個 chunk，文件已一併移除");
      } else {
        toast.success("已刪除 chunk");
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "刪除 chunk 失敗");
    } finally {
      setDeletingChunk(null);
    }
  }

  async function runQuery() {
    const query = queryText.trim();
    if (!query) {
      toast.error("請輸入要測試的問題");
      return;
    }

    setQuerying(true);
    setQueryError(null);
    try {
      const res = await fetch(`/api/knowledge/${collectionId}/query`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          query,
          topK: queryTopK !== "" ? Number(queryTopK) : 3,
          threshold: queryThreshold !== "" ? Number(queryThreshold) : 0.7,
        }),
      });
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new Error(
          data && typeof data.error === "string" ? data.error : "檢索失敗"
        );
      }
      setQueryResult(data as QueryResult);
    } catch (err) {
      const message = err instanceof Error ? err.message : "檢索失敗";
      setQueryError(message);
      setQueryResult(null);
    } finally {
      setQuerying(false);
    }
  }

  async function deleteCollection() {
    const ok = await confirmDialog({ title: "清空 RAG", description: `確定要刪除「${profileName}」的所有 RAG 內容嗎？此操作無法復原。`, confirmLabel: "清空" });
    if (!ok) return;
    setClearingCollection(true);
    try {
      const res = await fetch(`/api/knowledge/${collectionId}`, { method: "DELETE" });
      if (!res.ok) {
        const data = await res.json().catch(() => ({ error: "清空失敗" }));
        throw new Error(typeof data.error === "string" ? data.error : "清空失敗");
      }
      resetCollectionState();
      startTransition(() => router.refresh());
      toast.success(`已清空「${profileName}」的 RAG 內容`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "清空失敗");
    } finally {
      setClearingCollection(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold">{profileName} RAG</h1>
            <Badge
              variant={ragEnabled ? "secondary" : "outline"}
              className={ragEnabled ? "bg-green-500/10 text-green-700 dark:text-green-300" : ""}
            >
              {ragEnabled ? "已啟用檢索" : "未啟用檢索"}
            </Badge>
            {!collectionMatchesRole && (
              <Badge variant="destructive">collectionId 不一致</Badge>
            )}
          </div>
          <p className="text-xs text-muted-foreground">{collectionId}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => router.push(`/agents/${collectionId}`)}
          >
            <Settings2 className="size-4" />
            調整 RAG 設定
          </Button>
          <Button
            variant="destructive"
            size="sm"
            disabled={clearingCollection}
            onClick={deleteCollection}
          >
            {clearingCollection && <LoaderCircle className="size-4 animate-spin" />}
            {clearingCollection ? "清空中" : "清空 RAG"}
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="文件數"
          value={String(totalDocuments)}
          hint={`${indexedJobs} 份已索引${activeJobs > 0 ? `，${activeJobs} 份處理中` : ""}`}
        />
        <MetricCard
          label="Chunks"
          value={`${chunks.length}${chunksHasMore ? "+" : ""}`}
          hint={
            chunksHasMore
              ? "超過 500 筆，僅顯示前 500"
              : orphanChunks.length > 0
                ? `${orphanChunks.length} 個缺少文件紀錄`
                : "孤兒 0"
          }
        />
        <MetricCard
          label="失敗文件"
          value={String(failedJobs.length)}
          hint={failedJobs.length > 0 ? "需處理" : "正常"}
        />
        <MetricCard
          label="檢索設定"
          value={
            ragConfig ? `Top ${ragConfig.topK} / ${ragConfig.threshold.toFixed(2)}` : "未設定"
          }
          hint={ragEnabled ? "enabled" : "disabled"}
        />
      </div>

      <div>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database className="size-4" />
              目前設定
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex flex-wrap gap-2">
              <Badge
                variant={ragEnabled ? "secondary" : "outline"}
                className={ragEnabled ? "bg-green-500/10 text-green-700 dark:text-green-300" : ""}
              >
                {ragEnabled ? "RAG 啟用" : "RAG 停用"}
              </Badge>
              <Badge variant="outline">Top-K {ragConfig?.topK ?? 3}</Badge>
              <Badge variant="outline">Threshold {ragConfig?.threshold.toFixed(2) ?? "0.70"}</Badge>
            </div>
            {!collectionMatchesRole && (
              <Alert variant="destructive">
                <TriangleAlert className="size-4" />
                <AlertTitle>collectionId 不一致</AlertTitle>
                <AlertDescription>
                  Agent: `{ragConfig?.collectionId}`，目前頁面: `{collectionId}`。
                </AlertDescription>
              </Alert>
            )}
            {!ragEnabled && chunks.length > 0 && (
              <Alert>
                <TriangleAlert className="size-4" />
                <AlertTitle>RAG 停用</AlertTitle>
                <AlertDescription>已上傳內容不會進入對話檢索。</AlertDescription>
              </Alert>
            )}
            <Link
              href={`/agents/${collectionId}`}
              className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline"
            >
              前往 Agent 設定
              <ArrowUpRight className="size-4" />
            </Link>
          </CardContent>
        </Card>
      </div>

      <Tabs defaultValue="documents">
        <TabsList variant="line">
          <TabsTrigger value="documents">文件庫</TabsTrigger>
          <TabsTrigger value="query">檢索測試</TabsTrigger>
          <TabsTrigger value="diagnostics">診斷</TabsTrigger>
        </TabsList>

        <TabsContent value="documents" className="pt-2">
          <div className="grid gap-4 xl:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
            <Card className="h-fit">
              <CardHeader>
                <CardTitle>上傳文件</CardTitle>
                <CardDescription>支援 PDF、Markdown、TXT、DOCX，最大 20 MB。</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <input
                  ref={fileRef}
                  type="file"
                  accept=".pdf,.md,.txt,.docx"
                  className="hidden"
                  onChange={(e) => onFileSelect(e.target.files?.[0])}
                />

                <div
                  ref={dropRef}
                  onClick={() => !selectedFile && fileRef.current?.click()}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setIsDragging(true);
                  }}
                  onDragLeave={() => setIsDragging(false)}
                  onDrop={onDrop}
                  className={[
                    "relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-8 text-center transition-colors",
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
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedFile(null);
                          if (fileRef.current) fileRef.current.value = "";
                        }}
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
                          PDF、Markdown、TXT、DOCX / 20 MB
                        </p>
                      </div>
                    </>
                  )}
                </div>

                {uploading && (
                  <div className="space-y-1.5">
                    <Progress value={uploadProgress} className="h-1.5" />
                    <p className="text-xs text-muted-foreground text-center">上傳中…</p>
                  </div>
                )}

                {selectedFile && !uploading && (
                  <Button className="w-full gap-2" onClick={() => void handleUpload()}>
                    <Upload className="size-4" />
                    上傳「{selectedFile.name}」
                  </Button>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>文件庫</CardTitle>
                <CardDescription>
                  已上傳 {totalDocuments} 份文件，總共 {chunks.length}{chunksHasMore ? "+" : ""} 個 chunks。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {jobs.length === 0 && orphanEntries.length === 0 ? (
                  <p className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                    尚未上傳任何文件。
                  </p>
                ) : (
                  <div className="space-y-2">
                    {jobs.map((job) => {
                      const expanded = expandedJobs.has(job.id);
                      const jobChunks = chunksForJob(job);
                      const displayedChunkCount =
                        job.status === "done"
                          ? Math.max(job.chunkCount, jobChunks.length)
                          : job.chunkCount;
                      const canExpand = jobChunks.length > 0;

                      return (
                        <div key={job.id} className="overflow-hidden rounded-lg border border-border bg-card">
                          <div className="flex items-center gap-3 px-4 py-3">
                            <button
                              className="shrink-0 text-muted-foreground hover:text-foreground disabled:opacity-30"
                              disabled={!canExpand}
                              onClick={() => toggleExpand(job.id)}
                              aria-label={expanded ? "收合" : "展開"}
                            >
                              {expanded ? (
                                <ChevronDown className="size-4" />
                              ) : (
                                <ChevronRight className="size-4" />
                              )}
                            </button>

                            <span
                              className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${STATUS_COLOR[job.status] ?? "bg-muted text-muted-foreground"}`}
                            >
                              {STATUS_LABEL[job.status] ?? job.status}
                            </span>

                            <span className="flex-1 truncate font-medium">{job.fileName}</span>

                            <div className="flex shrink-0 items-center gap-3 text-sm text-muted-foreground">
                              {job.status === "done" && <span>{displayedChunkCount} chunks</span>}
                              {job.status === "processing" && (
                                <span className="inline-flex items-center gap-1">
                                  <LoaderCircle className="size-3.5 animate-spin" />
                                  處理中
                                </span>
                              )}
                              {job.error && (
                                <span
                                  className="max-w-xs truncate text-xs text-red-500"
                                  title={job.error}
                                >
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
                                <Trash2 className="size-4" />
                              </Button>
                            </div>
                          </div>

                          {expanded && (
                            <div className="divide-y divide-border border-t border-border">
                              {jobChunks.map((chunk, i) => (
                                <div
                                  key={chunk.id}
                                  className="flex items-start gap-3 bg-muted/30 px-4 py-3"
                                >
                                  <span className="w-6 shrink-0 pt-0.5 text-xs text-muted-foreground">
                                    #{i + 1}
                                  </span>
                                  <p className="flex-1 line-clamp-3 text-sm text-foreground">
                                    {chunk.content.slice(0, 300)}
                                    {chunk.content.length > 300 ? "…" : ""}
                                  </p>
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    className="h-7 w-7 shrink-0 p-0 text-muted-foreground/40 hover:text-destructive"
                                    disabled={deletingChunk === chunk.id}
                                    onClick={() => deleteChunk(chunk.id)}
                                    aria-label="刪除此 chunk"
                                  >
                                    <Trash2 className="size-3.5" />
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
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="query" className="pt-2">
          <div className="grid gap-4 xl:grid-cols-[minmax(0,380px)_minmax(0,1fr)]">
            <Card className="h-fit">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Search className="size-4" />
                  檢索測試
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <Textarea
                  value={queryText}
                  onChange={(e) => setQueryText(e.target.value)}
                  placeholder="輸入使用者可能會問的問題"
                  className="min-h-28"
                />

                <div className="grid grid-cols-2 gap-3">
                  <label className="space-y-1.5">
                    <span className="text-xs font-medium text-muted-foreground">Top-K</span>
                    <Input
                      type="number"
                      min={1}
                      max={20}
                      value={queryTopK}
                      onChange={(e) => setQueryTopK(e.target.value)}
                    />
                  </label>
                  <label className="space-y-1.5">
                    <span className="text-xs font-medium text-muted-foreground">
                      Threshold
                    </span>
                    <Input
                      type="number"
                      min={0}
                      max={1}
                      step={0.05}
                      value={queryThreshold}
                      onChange={(e) => setQueryThreshold(e.target.value)}
                    />
                  </label>
                </div>

                <Button
                  className="w-full"
                  disabled={querying || chunks.length === 0}
                  onClick={() => void runQuery()}
                >
                  {querying ? (
                    <LoaderCircle className="size-4 animate-spin" />
                  ) : (
                    <Search className="size-4" />
                  )}
                  執行檢索
                </Button>

                {chunks.length === 0 && (
                  <Alert>
                    <TriangleAlert className="size-4" />
                    <AlertTitle>無可檢索內容</AlertTitle>
                    <AlertDescription>請先上傳並完成 ingest。</AlertDescription>
                  </Alert>
                )}

                {queryError && (
                  <Alert variant="destructive">
                    <TriangleAlert className="size-4" />
                    <AlertTitle>檢索失敗</AlertTitle>
                    <AlertDescription>{queryError}</AlertDescription>
                  </Alert>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>命中結果</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {queryResult ? (
                  <>
                    <div className="grid gap-3 md:grid-cols-4">
                      <div className="rounded-lg border border-border px-3 py-2">
                        <p className="text-xs text-muted-foreground">Hit Count</p>
                        <p className="text-lg font-medium">{queryResult.metrics.hitCount}</p>
                      </div>
                      <div className="rounded-lg border border-border px-3 py-2">
                        <p className="text-xs text-muted-foreground">Top Similarity</p>
                        <p className="text-lg font-medium">
                          {queryResult.metrics.topSimilarity.toFixed(3)}
                        </p>
                      </div>
                      <div className="rounded-lg border border-border px-3 py-2">
                        <p className="text-xs text-muted-foreground">Latency</p>
                        <p className="text-lg font-medium">
                          {queryResult.metrics.latencyMs.toFixed(0)} ms
                        </p>
                      </div>
                      <div className="rounded-lg border border-border px-3 py-2">
                        <p className="text-xs text-muted-foreground">Query</p>
                        <p className="truncate text-sm font-medium" title={queryResult.query}>
                          {queryResult.query}
                        </p>
                      </div>
                    </div>

                    {queryResult.results.length === 0 ? (
                      <p className="rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
                        沒有找到任何 embedding chunk。
                      </p>
                    ) : (
                      <div className="space-y-3">
                        {queryResult.results.map((hit, index) => (
                          <div
                            key={hit.id}
                            className="rounded-lg border border-border bg-muted/20 p-4"
                          >
                            <div className="mb-3 flex flex-wrap items-center gap-2">
                              <Badge variant={hit.passedThreshold ? "secondary" : "outline"}>
                                #{index + 1}
                              </Badge>
                              <Badge
                                variant={hit.passedThreshold ? "secondary" : "outline"}
                                className={
                                  hit.passedThreshold
                                    ? "bg-green-500/10 text-green-700 dark:text-green-300"
                                    : ""
                                }
                              >
                                {hit.similarity.toFixed(3)}
                              </Badge>
                              {!hit.passedThreshold && (
                                <Badge variant="outline">低於門檻</Badge>
                              )}
                              <span className="truncate text-xs text-muted-foreground">
                                {sourceFromMetadata(hit.metadata)}
                              </span>
                            </div>
                            <p className="whitespace-pre-wrap text-sm leading-6">
                              {hit.content}
                            </p>
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Clock3 className="size-3.5" />
                      embedding {queryResult.metrics.embeddingMs.toFixed(0)} ms, db{" "}
                      {queryResult.metrics.dbMs.toFixed(0)} ms
                    </div>
                  </>
                ) : (
                  <p className="rounded-lg border border-dashed border-border px-4 py-12 text-center text-sm text-muted-foreground">
                    尚未執行檢索。
                  </p>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="diagnostics" className="pt-2">
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.9fr)]">
            <Card>
              <CardHeader>
                <CardTitle>索引健康度</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {chunksHasMore && (
                  <Alert variant="destructive">
                    <TriangleAlert className="size-4" />
                    <AlertTitle>診斷資料不完整</AlertTitle>
                    <AlertDescription>
                      Chunks 超過 500 筆，孤兒偵測與 chunk 計數僅基於前 500 筆，結果可能不準確。
                    </AlertDescription>
                  </Alert>
                )}
                {activeJobs > 0 && (
                  <Alert>
                    <LoaderCircle className="size-4 animate-spin" />
                    <AlertTitle>Ingest 中</AlertTitle>
                    <AlertDescription>{activeJobs} 份文件處理中。</AlertDescription>
                  </Alert>
                )}

                {failedJobs.length > 0 ? (
                  <Alert variant="destructive">
                    <TriangleAlert className="size-4" />
                    <AlertTitle>有 {failedJobs.length} 份文件處理失敗</AlertTitle>
                    <AlertDescription>
                      {failedJobs.map((job) => `${job.fileName}${job.error ? `: ${job.error}` : ""}`).join("；")}
                    </AlertDescription>
                  </Alert>
                ) : (
                  <Alert>
                    <CheckCircle2 className="size-4" />
                    <AlertTitle>沒有 ingest 失敗</AlertTitle>
                  </Alert>
                )}

                {orphanEntries.length > 0 ? (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <Badge variant="destructive">需要清理</Badge>
                      <p className="text-sm font-medium">孤兒 chunks</p>
                    </div>
                    <div className="space-y-2">
                      {orphanEntries.map(([src, grpChunks]) => {
                        const key = `orphan-${src}`;
                        const expanded = expandedJobs.has(key);
                        return (
                          <div
                            key={key}
                            className="overflow-hidden rounded-lg border border-dashed border-border bg-card"
                          >
                            <div className="flex items-center gap-3 px-4 py-3">
                              <button
                                className="shrink-0 text-muted-foreground hover:text-foreground"
                                onClick={() => toggleExpand(key)}
                                aria-label={expanded ? "收合" : "展開"}
                              >
                                {expanded ? (
                                  <ChevronDown className="size-4" />
                                ) : (
                                  <ChevronRight className="size-4" />
                                )}
                              </button>
                              <Badge variant="outline">無紀錄</Badge>
                              <span className="flex-1 truncate font-medium text-muted-foreground">
                                {src}
                              </span>
                              <span className="shrink-0 text-sm text-muted-foreground">
                                {grpChunks.length} chunks
                              </span>
                              <Button
                                variant="ghost"
                                size="sm"
                                className="h-7 w-7 shrink-0 p-0 text-muted-foreground hover:text-destructive"
                                onClick={async () => {
                                  const ok = await confirmDialog({
                                    description: `確定要刪除「${src}」的所有 chunks 嗎？`,
                                    confirmLabel: "刪除",
                                  });
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
                                  await syncAfterMutation();
                                }}
                                aria-label="刪除此群組所有 chunks"
                              >
                                <Trash2 className="size-4" />
                              </Button>
                            </div>
                            {expanded && (
                              <div className="divide-y divide-border border-t border-border">
                                {grpChunks.map((chunk, i) => (
                                  <div
                                    key={chunk.id}
                                    className="flex items-start gap-3 bg-muted/30 px-4 py-3"
                                  >
                                    <span className="w-6 shrink-0 pt-0.5 text-xs text-muted-foreground">
                                      #{i + 1}
                                    </span>
                                    <p className="flex-1 line-clamp-3 text-sm text-foreground">
                                      {chunk.content.slice(0, 300)}
                                      {chunk.content.length > 300 ? "…" : ""}
                                    </p>
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      className="h-7 w-7 shrink-0 p-0 text-muted-foreground/40 hover:text-destructive"
                                      disabled={deletingChunk === chunk.id}
                                      onClick={() => deleteChunk(chunk.id)}
                                      aria-label="刪除此 chunk"
                                    >
                                      <Trash2 className="size-3.5" />
                                    </Button>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ) : (
                  <Alert>
                    <CheckCircle2 className="size-4" />
                    <AlertTitle>沒有孤兒 chunks</AlertTitle>
                  </Alert>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Collection 資訊</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                <div className="rounded-lg border border-border p-4">
                  <div className="space-y-1 text-muted-foreground">
                    <p>Role: {profileName}</p>
                    <p>Collection ID: {collectionId}</p>
                    <p>RAG 啟用: {ragEnabled ? "是" : "否"}</p>
                    <p>Top-K: {ragConfig?.topK ?? 3}</p>
                    <p>Threshold: {ragConfig?.threshold.toFixed(2) ?? "0.70"}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
