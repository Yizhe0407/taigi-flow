import { z } from "zod";

export const voiceConfigSchema = z.object({
  piperModel: z.string().min(1),
  speed: z.number().positive().default(1.0),
  pitch: z.number().default(0),
});
export type VoiceConfig = z.infer<typeof voiceConfigSchema>;

export const ragConfigSchema = z
  .object({
    collectionId: z.string().min(1),
    topK: z.number().int().positive().default(4),
  })
  .nullable();
export type RagConfig = z.infer<typeof ragConfigSchema>;

export const toolsSchema = z.array(z.string());
export type Tools = z.infer<typeof toolsSchema>;

export const agentProfileCreateSchema = z.object({
  name: z.string().min(1).max(80),
  description: z.string().nullable().optional(),
  systemPrompt: z.string().min(1),
  voiceConfig: voiceConfigSchema,
  ragConfig: ragConfigSchema.optional(),
  tools: toolsSchema.default([]),
  isActive: z.boolean().default(true),
});
export type AgentProfileCreateInput = z.infer<typeof agentProfileCreateSchema>;

export const agentProfileUpdateSchema = agentProfileCreateSchema.partial();
export type AgentProfileUpdateInput = z.infer<typeof agentProfileUpdateSchema>;

export const pronunciationCreateSchema = z.object({
  profileId: z.string().uuid().nullable().optional(),
  term: z.string().min(1).max(200),
  replacement: z.string().min(1).max(200),
  priority: z.number().int().default(0),
  note: z.string().nullable().optional(),
});
export type PronunciationCreateInput = z.infer<typeof pronunciationCreateSchema>;

export const pronunciationUpdateSchema = pronunciationCreateSchema.partial();
export type PronunciationUpdateInput = z.infer<typeof pronunciationUpdateSchema>;

export const pronunciationFromLogSchema = z.object({
  logId: z.string().uuid(),
  term: z.string().min(1),
  replacement: z.string().min(1),
  profileId: z.string().uuid().nullable().optional(),
  priority: z.number().int().default(0),
  note: z.string().nullable().optional(),
});
export type PronunciationFromLogInput = z.infer<typeof pronunciationFromLogSchema>;

export const sessionListQuerySchema = z.object({
  limit: z.coerce.number().int().min(1).max(200).default(50),
  cursor: z.string().uuid().optional(),
  agentProfileId: z.string().uuid().optional(),
  hasError: z.coerce.boolean().optional(),
});
export type SessionListQuery = z.infer<typeof sessionListQuerySchema>;

export const turnFilterSchema = z.object({
  bargedIn: z.coerce.boolean().optional(),
  hasError: z.coerce.boolean().optional(),
  minLatencyMs: z.coerce.number().int().nonnegative().optional(),
});
export type TurnFilter = z.infer<typeof turnFilterSchema>;
