import { createBrowserRouter, Navigate } from 'react-router-dom'
import { RootLayout } from '../components/layout/RootLayout'
import { QueryConsolePage } from '../components/query/QueryConsolePage'
import { AdminConsolePage } from '../components/admin/AdminConsolePage'
import { LoginPage } from '../components/auth/LoginPage'
import { RegisterPage } from '../components/auth/RegisterPage'
import { RequireAdmin } from '../components/auth/RequireAdmin'
import { RequireAuth } from '../components/auth/RequireAuth'

export const AppRouter = createBrowserRouter([
  {
    path: '/',
    element: <RootLayout />,
    children: [
      {
        index: true,
        element: (
          <RequireAuth>
            <QueryConsolePage />
          </RequireAuth>
        ),
      },
      {
        path: 'login',
        element: <LoginPage />,
      },
      {
        path: 'register',
        element: <RegisterPage />,
      },
      {
        path: 'admin/:section?',
        element: (
          <RequireAdmin>
            <AdminConsolePage />
          </RequireAdmin>
        ),
      },
      {
        path: '*',
        element: <Navigate to="/" replace />,
      },
    ],
  },
])
