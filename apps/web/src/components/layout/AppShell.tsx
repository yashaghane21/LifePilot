import { useEffect, useState } from 'react'
import { Outlet } from 'react-router'
import { ConversationsProvider } from '../../features/assistant/ConversationsProvider'
import { Sidebar } from './Sidebar'

const SIDEBAR_KEY = 'lifepilot.sidebarCollapsed'

function initialCollapsed(): boolean {
  try {
    const saved = localStorage.getItem(SIDEBAR_KEY)
    if (saved !== null) return saved === 'true'
  } catch {
    // Storage unavailable: fall through to the screen-size default.
  }
  return window.matchMedia('(max-width: 768px)').matches
}

/** Full-height app frame: sidebar on the left, the current page scrolling on the right. */
export function AppShell() {
  const [collapsed, setCollapsed] = useState(initialCollapsed)

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, String(collapsed))
    } catch {
      // Not persisted; the sidebar still works for this visit.
    }
  }, [collapsed])

  return (
    // Conversations are loaded once here, shared by the sidebar list and the assistant page.
    <ConversationsProvider>
      <div className="flex h-screen overflow-hidden bg-canvas">
        <Sidebar collapsed={collapsed} onToggle={() => setCollapsed((c) => !c)} />
        <main className="min-w-0 flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </ConversationsProvider>
  )
}
