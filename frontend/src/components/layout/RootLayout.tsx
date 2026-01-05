import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'

export function RootLayout() {
  useEffect(() => {
    if (typeof window === 'undefined' || typeof document === 'undefined') return
    const applyHeight = () => {
      document.documentElement.style.setProperty('--app-height', `${window.innerHeight}px`)
    }
    applyHeight()
    window.addEventListener('resize', applyHeight)
    return () => {
      window.removeEventListener('resize', applyHeight)
    }
  }, [])

  return (
    <main className="relative flex min-h-screen flex-col">
      <Outlet />
    </main>
  )
}
