import { useEffect, useMemo, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { fetchAdminStopList, updateAdminStopList } from '../../services/apiClient'

const parseLines = (value: string) =>
  value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)

export function StopListManager({ readOnly = false }: { readOnly?: boolean }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState<{ tone: 'info' | 'error'; message: string } | null>(null)

  const stopQuery = useQuery({
    queryKey: ['admin-stop-list'],
    queryFn: fetchAdminStopList,
    staleTime: 1000 * 15,
  })

  useEffect(() => {
    if (!stopQuery.data) return
    setText((stopQuery.data.items ?? []).join('\n'))
  }, [stopQuery.data])

  const stats = useMemo(() => {
    const items = parseLines(text)
    const unique = Array.from(new Set(items))
    return { count: items.length, uniqueCount: unique.length, unique }
  }, [text])

  const save = async () => {
    if (readOnly) return
    setBusy(true)
    setStatus(null)
    try {
      const updated = await updateAdminStopList(stats.unique)
      setText(updated.items.join('\n'))
      await queryClient.invalidateQueries({ queryKey: ['admin-stop-list'] })
      await queryClient.invalidateQueries({ queryKey: ['metrics'] })
      setStatus({ tone: 'info', message: t('admin.stop_list.status.saved', { count: updated.items.length }) })
    } catch (e) {
      setStatus({ tone: 'error', message: e instanceof Error ? e.message : t('admin.stop_list.error.save') })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mt-6">
      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">{t('admin.stop_list.title')}</h3>
            <p className="mt-1 text-xs text-slate-500">{t('admin.stop_list.subtitle')}</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
              onClick={() => void stopQuery.refetch()}
              disabled={stopQuery.isLoading}
            >
              {t('common.refresh')}
            </button>
            <button
              type="button"
              className="rounded-full bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
              onClick={() => void save()}
              disabled={busy || readOnly}
            >
              {t('common.save')}
            </button>
          </div>
        </div>

        {stopQuery.isLoading ? <p className="mt-4 text-sm text-slate-500">{t('common.loading')}</p> : null}
        {stopQuery.error ? <p className="mt-4 text-sm text-rose-600">{String(stopQuery.error)}</p> : null}

        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_220px]">
          <div>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              className="h-[420px] w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-slate-200"
              placeholder={t('admin.stop_list.placeholder')}
              disabled={busy || readOnly}
            />
          </div>
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">{t('admin.stop_list.summary')}</p>
            <div className="mt-3 space-y-2 text-sm text-slate-700">
              <p>
                <span className="font-semibold">{t('admin.stop_list.lines')}</span>: {stats.count}
              </p>
              <p>
                <span className="font-semibold">{t('admin.stop_list.unique')}</span>: {stats.uniqueCount}
              </p>
            </div>
            <p className="mt-4 text-xs text-slate-500">{t('admin.stop_list.save_hint')}</p>
          </div>
        </div>

        {status ? (
          <p className={`mt-4 text-sm ${status.tone === 'error' ? 'text-rose-600' : 'text-slate-600'}`}>{status.message}</p>
        ) : null}
      </section>
    </div>
  )
}

