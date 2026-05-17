import { prisma } from "@taigi-flow/db";
import { PageHeader } from "@/components/page-header";
import KnowledgeList from "./_components/KnowledgeList";

export const dynamic = "force-dynamic";

export default async function KnowledgePage() {
  const profiles = await prisma.agentProfile.findMany({
    orderBy: { name: "asc" },
    select: { id: true, name: true, ragConfig: true },
  });

  const counts = await Promise.all(
    profiles.map((p) =>
      prisma.$queryRaw<[{ count: bigint }]>`
        SELECT COUNT(*)::bigint AS count FROM "KnowledgeChunk" WHERE "collectionId" = ${p.id}
      `.then((r) => Number(r[0].count))
    )
  );

  const items = profiles.map((p, i) => ({
    id: p.id,
    name: p.name,
    ragEnabled: (p.ragConfig as { enabled?: boolean } | null)?.enabled ?? false,
    chunkCount: counts[i],
  }));

  return (
    <div>
      <PageHeader
        title="RAG"
        description="每個 Role 對應一個 RAG 知識庫（collection ID = Role ID）"
      />
      <KnowledgeList items={items} />
    </div>
  );
}
