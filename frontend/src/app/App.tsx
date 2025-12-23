import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Suspense } from 'react'
import { RouterProvider } from 'react-router-dom'
import { AppRouter } from './routes'
import '../index.css'

const queryClient = new QueryClient()

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Suspense fallback={<div className="flex items-center justify-center py-20 text-sm text-slate-500">Loading¡­</div>}>
        <RouterProvider router={AppRouter} />
      </Suspense>
    </QueryClientProvider>
  )
}

export default App

