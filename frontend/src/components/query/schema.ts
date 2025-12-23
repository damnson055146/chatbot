import { z } from 'zod'

export const queryFormSchema = z.object({
  question: z
    .string()
    .min(5, 'Question must be at least 5 characters long.')
    .max(2000, 'Question must be shorter than 2000 characters.'),
  language: z.enum(['auto', 'en', 'zh']).default('auto'),
  explain_like_new: z.boolean().optional().default(false),
  top_k: z.coerce
    .number()
    .min(1, 'Top K must be >= 1')
    .max(20, 'Top K must be <= 20')
    .default(8),
  k_cite: z.coerce
    .number()
    .min(1, 'k_cite must be >= 1')
    .max(10, 'k_cite must be <= 10')
    .default(2),
})

export type QueryFormValues = z.infer<typeof queryFormSchema>
