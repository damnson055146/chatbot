import { z } from 'zod'
import { i18next } from '../../utils/i18n'

export const queryFormSchema = z.object({
  question: z
    .string()
    .min(5, i18next.t('query.validation.question_min', { min: 5 }))
    .max(2000, i18next.t('query.validation.question_max', { max: 2000 })),
  language: z.enum(['auto', 'en', 'zh']).default('auto'),
  explain_like_new: z.boolean().optional().default(false),
  top_k: z.coerce
    .number()
    .min(1, i18next.t('query.validation.top_k_min', { min: 1 }))
    .max(20, i18next.t('query.validation.top_k_max', { max: 20 }))
    .default(8),
  k_cite: z.coerce
    .number()
    .min(1, i18next.t('query.validation.k_cite_min', { min: 1 }))
    .max(10, i18next.t('query.validation.k_cite_max', { max: 10 }))
    .default(2),
})

export type QueryFormValues = z.infer<typeof queryFormSchema>
