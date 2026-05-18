import { prisma } from "@taigi-flow/db";
import { notFound } from "next/navigation";
import AgentForm from "../_components/AgentForm";

export const dynamic = "force-dynamic";

const CHUNK_LIMIT = 500;

export default async function EditAgentPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const [profile, rawChunks, jobs] = await Promise.all([
    prisma.agentProfile.findUnique({ where: { id } }),
    prisma.$queryRaw<
      { id: string; content: string; metadata: Record<string, unknown>; createdAt: Date }[]
    >`
      SELECT id, content, metadata, "createdAt"
      FROM "KnowledgeChunk"
      WHERE "collectionId" = ${id}
      ORDER BY "createdAt" ASC
      LIMIT ${CHUNK_LIMIT + 1}
    `,
    prisma.ingestJob.findMany({
      where: { collectionId: id },
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

  if (!profile) notFound();

  const chunksHasMore = rawChunks.length > CHUNK_LIMIT;
  const chunks = chunksHasMore ? rawChunks.slice(0, CHUNK_LIMIT) : rawChunks;

  return (
    <AgentForm
      profile={profile}
      knowledgeData={{ initialChunks: chunks, initialChunksHasMore: chunksHasMore, initialJobs: jobs }}
    />
  );
}
