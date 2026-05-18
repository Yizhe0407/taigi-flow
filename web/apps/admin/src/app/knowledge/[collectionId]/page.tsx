import { redirect } from "next/navigation";

type Props = { params: Promise<{ collectionId: string }> };

export default async function KnowledgeCollectionPage({ params }: Props) {
  const { collectionId } = await params;
  redirect(`/agents/${collectionId}`);
}
