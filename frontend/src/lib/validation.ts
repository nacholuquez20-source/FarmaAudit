import { z } from 'zod';

const MIN_COMMENT_LENGTH = 10;
const MAX_COMMENT_LENGTH = 2000;
const MAX_EVIDENCE_TEXT_LENGTH = 500;
const MAX_URL_LENGTH = 2048;

export const ResolutionFormSchema = z.object({
  resolutionComment: z
    .string()
    .min(MIN_COMMENT_LENGTH, `El comentario debe tener al menos ${MIN_COMMENT_LENGTH} caracteres.`)
    .max(MAX_COMMENT_LENGTH, `El comentario no puede exceder ${MAX_COMMENT_LENGTH} caracteres.`)
    .trim(),
  evidenceText: z
    .string()
    .max(MAX_EVIDENCE_TEXT_LENGTH, `La evidencia no puede exceder ${MAX_EVIDENCE_TEXT_LENGTH} caracteres.`)
    .trim()
    .optional()
    .or(z.literal('')),
  evidenceUrl: z
    .string()
    .max(MAX_URL_LENGTH, `La URL no puede exceder ${MAX_URL_LENGTH} caracteres.`)
    .refine((url) => !url.trim() || /^https?:\/\/.+/.test(url.trim()), 'La URL debe ser http o https válida.')
    .optional()
    .or(z.literal('')),
});

export function validateResolutionForm(data: unknown) {
  try {
    return ResolutionFormSchema.parse(data);
  } catch (error) {
    if (error instanceof z.ZodError) {
      return { error: error.issues[0]?.message || 'Validación fallida.' };
    }
    return { error: 'Error validando el formulario.' };
  }
}
