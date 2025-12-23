import { Link } from 'react-router-dom'

export function PlaceholderPage({
  title,
  description,
  backTo = '/',
  backLabel = 'Back',
}: {
  title: string
  description?: string
  backTo?: string
  backLabel?: string
}) {
  return (
    <div className="min-h-screen bg-[#F7F7F8] text-slate-900">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-4">
          <div>
            <p className="text-[11px] uppercase tracking-[0.4em] text-slate-400">Workspace</p>
            <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
          </div>
          <Link
            to={backTo}
            className="rounded-full border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:border-slate-400"
          >
            {backLabel}
          </Link>
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl px-6 py-10">
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <p className="text-sm text-slate-700">{description ?? 'This section is under construction.'}</p>
        </section>
      </main>
    </div>
  )
}


