import { Outlet } from 'react-router-dom'

export function RootLayout() {
  return (
    <div className="min-h-screen bg-[#F7F7F8] text-slate-900">
      <main className="flex min-h-screen flex-col">
        <Outlet />
      </main>
    </div>
  )
}
