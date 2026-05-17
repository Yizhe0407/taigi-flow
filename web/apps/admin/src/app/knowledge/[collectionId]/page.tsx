import { prisma } from "@taigi-flow/db";
import { notFound } from "next/navigation";
import KnowledgeCollection from "./_components/KnowledgeCollection";

export const dynamic = "force-dynamic";

type Props = { params: Promise<{ collectionId: string }> };

export default async function KnowledgeCollectionPage({ params }: Props) {
  const { collectionId } = await params;

  const profile = await prisma.agentProfile.findUnique({
    where: { id: collectionId },
    select: { id: true, name: true },
  });
  if (!profile) notFound();

  const [chunks, jobs] = await Promise.all([
    prisma.$queryRaw<
      { id: string; content: string; metadata: Record<string, unknown>; createdAt: Date }[]
    >`
      SELECT id, content, metadata, "createdAt"
      FROM "KnowledgeChunk"
      WHERE "collectionId" = ${collectionId}
      ORDER BY "createdAt" ASC
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

  return (
    <KnowledgeCollection
      profileName={profile.name}
      collectionId={collectionId}
      initialChunks={chunks}
      initialJobs={jobs}
    />
  );
}
