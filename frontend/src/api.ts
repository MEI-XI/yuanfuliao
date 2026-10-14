import { z } from 'zod'

export const userSchema = z.object({ id: z.number(), username: z.string(), role: z.enum(['admin', 'user']), active: z.boolean() })
export const ledgerSchema = z.object({ id: z.number(), name: z.string() })
export const itemSchema = z.object({ name: z.string().default(''), standard: z.string().default(''), unit: z.string().default(''), result: z.string().default(''), conclusion: z.string().default('') })
export const fieldsSchema = z.object({
  arrival_date: z.string().nullable().default(null), material_name: z.string().default(''),
  production_dates: z.array(z.string()).default([]), specification: z.string().default(''), company_name: z.string().default(''),
  address: z.string().default(''), contact: z.string().default(''), shelf_life: z.string().default(''),
  received_quantity: z.string().default(''), certificates: z.string().default(''), sensory: z.string().default(''),
  sampling_items: z.string().default(''), notes: z.string().default(''),
  address_source: z.enum(['', 'supplier', 'manufacturer']).default(''), contact_source: z.enum(['', 'supplier', 'manufacturer']).default(''),
})
export const reportSchema = z.object({ packaging: z.string().default(''), basis: z.string().default(''), inspection_date: z.string().nullable().default(null), internal_report: z.string().default(''), conclusion: z.string().default(''), inspector: z.string().default(''), approver: z.string().default('') })
export const recordSchema = z.object({
  id: z.number(), ledger_id: z.number(), creator_id: z.number(), version: z.number(),
  status: z.enum(['pending', 'checked', 'void']), fields: fieldsSchema, items: z.array(itemSchema), report: reportSchema,
  image_ids: z.array(z.number()), material_id: z.number().nullable(), scheme_name: z.string(),
  recognition_job_id: z.number().nullable().default(null),
  created_at: z.string(), updated_at: z.string(), checker_id: z.number().nullable(), checked_at: z.string().nullable(),
})
export type User = z.infer<typeof userSchema>
export type Ledger = z.infer<typeof ledgerSchema>
export type CheckRecord = z.infer<typeof recordSchema>
export type Fields = z.infer<typeof fieldsSchema>
export type Item = z.infer<typeof itemSchema>
const suggestionSchema = z.object({
  material_name: z.string(), production_dates: z.array(z.string()), specification: z.string(), company_name: z.string(),
  address: z.string(), contact: z.string(), shelf_life: z.string(),
  address_source: z.enum(['', 'supplier', 'manufacturer']), contact_source: z.enum(['', 'supplier', 'manufacturer']),
}).partial()
export const jobSchema = z.object({
  id: z.number(), image_ids: z.array(z.number()), local_status: z.enum(['queued', 'running', 'done', 'failed']),
  cloud_status: z.enum(['disabled', 'queued', 'running', 'done', 'failed']),
  fields: suggestionSchema, cloud_fields: suggestionSchema,
  evidence: z.array(z.object({ texts: z.array(z.string()), boxes: z.array(z.unknown()),
    supplements: z.array(z.object({ texts: z.array(z.string()), kind: z.string() })).default([]) })),
  conflicts: z.record(z.string(), z.array(z.string())), error: z.string(), cloud_error: z.string(),
  queue_ahead: z.number().default(0),
  review_suggestions: z.object({
    fields: suggestionSchema,
    conflicts: z.record(z.string(), z.array(z.string())),
    sources: z.array(z.object({ record_id: z.number(), version: z.number(), ledger_name: z.string(), checked_at: z.string() })),
  }).default({ fields: {}, conflicts: {}, sources: [] }),
})
export type Job = z.infer<typeof jobSchema>
export const materialSchema = z.object({ id: z.number(), name: z.string(), model: z.string(), aliases: z.string() })
export const schemeSchema = z.object({ id: z.number(), material_id: z.number().nullable(), name: z.string(), items: z.array(itemSchema) })
export const partnerSchema = z.object({ id: z.number(), name: z.string(), kind: z.enum(['supplier', 'manufacturer']), address: z.string(), contact: z.string() })

export async function raw(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const response = await fetch('/api' + path, { ...init, headers })
  if (!response.ok) {
    const result: unknown = await response.json().catch(() => null)
    const error = z.object({ detail: z.string() }).safeParse(result)
    throw new Error(error.success ? error.data.detail : `操作失败（${response.status}），请检查填写内容`)
  }
  return response
}

export async function api<T>(path: string, schema: z.ZodType<T>, init: RequestInit = {}): Promise<T> {
  const response = await raw(path, init)
  return schema.parse(await response.json())
}

export function json(method: string, body: unknown): RequestInit {
  return { method, body: JSON.stringify(body) }
}

export function today() {
  const parts = new Intl.DateTimeFormat('en', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
  const part = (name: string) => parts.find(p => p.type === name)?.value || ''
  return `${part('year')}-${part('month')}-${part('day')}`
}
