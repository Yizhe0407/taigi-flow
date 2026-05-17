import { prisma } from "@taigi-flow/db";
import DictionaryManager from "./_components/DictionaryManager";

export const dynamic = "force-dynamic";

export default async function DictionaryPage() {
  const [globalEntries, agents] = await Promise.all([
    prisma.pronunciationEntry.findMany({
      where: { profileId: null },
      orderBy: [{ priority: "desc" }, { term: "asc" }],
    }),
    prisma.agentProfile.findMany({
      orderBy: { name: "asc" },
      select: { id: true, name: true },
      where: {},
    }),
  ]);

  return <DictionaryManager globalEntries={globalEntries} agents={agents} />;
}
