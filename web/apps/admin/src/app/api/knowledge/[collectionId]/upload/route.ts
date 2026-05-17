import { writeFile, mkdir, unlink } from "fs/promises";
import path from "path";

import { prisma } from "@taigi-flow/db";
import { error, handleError, ok } from "@/lib/api";

export const dynamic = "force-dynamic";

const UPLOAD_DIR = process.env.INGEST_UPLOAD_DIR ?? "/tmp/taigi-ingest";
const ALLOWED_EXTS = new Set([".pdf", ".md", ".txt", ".docx"]);
const MAX_BYTES = 20 * 1024 * 1024; // 20 MB

type Ctx = { params: Promise<{ collectionId: string }> };

export async function POST(req: Request, { params }: Ctx): Promise<Response> {
  try {
    const { collectionId } = await params;

    const profile = await prisma.agentProfile.findUnique({
      where: { id: collectionId },
      select: { id: true },
    });
    if (!profile) return error("Collection (AgentProfile) not found", 404);

    const formData = await req.formData();
    const file = formData.get("file");
    if (!(file instanceof File)) return error("file field required", 400);

    const ext = path.extname(file.name).toLowerCase();
    if (!ALLOWED_EXTS.has(ext)) {
      return error(`Unsupported file type ${ext}. Allowed: pdf, md, txt, docx`, 400);
    }

    const buffer = Buffer.from(await file.arrayBuffer());
    if (buffer.byteLength > MAX_BYTES) {
      return error("File exceeds 20 MB limit", 400);
    }

    const collDir = path.join(UPLOAD_DIR, collectionId);
    await mkdir(collDir, { recursive: true });
    const safeName = `${Date.now()}-${file.name.replace(/[^a-zA-Z0-9._-]/g, "_")}`;
    const filePath = path.join(collDir, safeName);
    await writeFile(filePath, buffer);

    let job;
    try {
      job = await prisma.ingestJob.create({
        data: {
          collectionId,
          fileName: file.name,
          filePath,
          status: "pending",
        },
      });
    } catch (err) {
      await unlink(filePath).catch(() => {});
      throw err;
    }

    return ok(job, { status: 201 });
  } catch (err) {
    return handleError(err);
  }
}
