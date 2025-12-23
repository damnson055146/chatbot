import { createBrowserRouter, Navigate } from 'react-router-dom'
import { RootLayout } from '../components/layout/RootLayout'
import { QueryConsolePage } from '../components/query/QueryConsolePage'
import { AdminConsolePage } from '../components/admin/AdminConsolePage'
import { PlaceholderPage } from '../components/pages/PlaceholderPage'

export const AppRouter = createBrowserRouter([
  {
    path: '/',
    element: <RootLayout />,
    children: [
      {
        index: true,
        element: <QueryConsolePage />,
      },
      {
        path: 'admin/:section?',
        element: <AdminConsolePage />,
      },
      {
        path: 'library',
        element: <PlaceholderPage title="Library" description="Curated sources and uploaded artefacts will appear here." backTo="/" backLabel="Back to chat" />,
      },
      {
        path: 'explore',
        element: <PlaceholderPage title="Explore" description="Discovery workflows and templates will appear here." backTo="/" backLabel="Back to chat" />,
      },
      {
        path: 'release-notes',
        element: <PlaceholderPage title="Release notes" description="Changelog and deployment notes will appear here." backTo="/" backLabel="Back to chat" />,
      },
      {
        path: '*',
        element: <Navigate to="/" replace />,
      },
    ],
  },
])
