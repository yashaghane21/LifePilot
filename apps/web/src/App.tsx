import { createBrowserRouter, Link, RouterProvider } from 'react-router'
import { AuthProvider } from './auth/AuthProvider'
import { PublicOnly, RequireAuth } from './auth/guards'
import { AppShell } from './components/layout/AppShell'
import { AssistantPage } from './features/assistant/AssistantPage'
import { LoginPage } from './features/auth/LoginPage'
import { RegisterPage } from './features/auth/RegisterPage'
import { DashboardPage } from './features/dashboard/DashboardPage'
import { FinancePage } from './features/finance/FinancePage'
import { SettingsPage } from './features/settings/SettingsPage'
import { ThemeProvider } from './theme/ThemeProvider'

const router = createBrowserRouter([
  {
    element: <PublicOnly />,
    children: [
      { path: 'login', element: <LoginPage /> },
      { path: 'register', element: <RegisterPage /> },
    ],
  },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <DashboardPage /> },
          { path: 'assistant', element: <AssistantPage /> },
          { path: 'assistant/:conversationId', element: <AssistantPage /> },
          { path: 'finance', element: <FinancePage /> },
          { path: 'settings', element: <SettingsPage /> },
          { path: '*', element: <NotFound /> },
        ],
      },
    ],
  },
])

function NotFound() {
  return (
    <div className="flex flex-col gap-3 p-10">
      <h1 className="m-0 text-2xl font-semibold">Page not found</h1>
      <Link to="/" className="text-accent hover:text-accent-hover">
        Back to the dashboard
      </Link>
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <RouterProvider router={router} />
      </AuthProvider>
    </ThemeProvider>
  )
}
