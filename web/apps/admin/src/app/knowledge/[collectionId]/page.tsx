import { prisma } from "@taigi-flow/db";
import { notFound } from "next/navigation";
import KnowledgeCollection from "./_components/KnowledgeCollection";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ collectionId: string }> };

export default async function KnowledgeCollectionPage({ params }: Props) {
  const { collectionId } = await params;

  const profile = await prisma.agentProfile.findUnique({
    where: { id: collectionId },
    select: { id: true, name: true, ragConfig: true },
  });
  if (!profile) notFound();

  const rawRagConfig =
    profile.ragConfig && typeof profile.ragConfig === "object"
      ? (profile.ragConfig as Record<string, unknown>)
      : null;
  const ragConfig = rawRagConfig
    ? {
        enabled: rawRagConfig.enabled === true,
        topK:
          typeof rawRagConfig.topK === "number" && Number.isFinite(rawRagConfig.topK)
            ? rawRagConfig.topK
            : 3,
        threshold:
          typeof rawRagConfig.threshold === "number" &&
          Number.isFinite(rawRagConfig.threshold)
            ? rawRagConfig.threshold
            : 0.7,
        collectionId:
          typeof rawRagConfig.collectionId === "string"
            ? rawRagConfig.collectionId
            : collectionId,
      }
    : null;

  const CHUNK_LIMIT = 500;
  const [rawChunks, jobs] = await Promise.all([
    prisma.$queryRaw<
      { id: string; content: string; metadata: Record<string, unknown>; createdAt: Date }[]
    >`
      SELECT id, content, metadata, "createdAt"
      FROM "KnowledgeChunk"
      WHERE "collectionId" = ${collectionId}
      ORDER BY "createdAt" ASC
      LIMIT ${CHUNK_LIMIT + 1}
    `,
    prisma.ingestJob.findMany({
      where: { collectionId },
      orderBy: { createdAt: "desc" },
      take: 100,
      select: {
        id: true,
        fileName: true,
        filePath: true,
        status: true,
        chunkCount: true,
        error: true,
        createdAt: true,
      },
    }),
  ]);

  const chunksHasMore = rawChunks.length > CHUNK_LIMIT;
  const chunks = chunksHasMore ? rawChunks.slice(0, CHUNK_LIMIT) : rawChunks;

  return (
    <KnowledgeCollection
      profileName={profile.name}
      collectionId={collectionId}
      ragConfig={ragConfig}
      initialChunks={chunks}
      initialChunksHasMore={chunksHasMore}
      initialJobs={jobs}
    />
  );
}
