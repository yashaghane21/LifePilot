import { NavLink, useNavigate, useParams } from 'react-router'
import { useAuth, useCurrentUser } from '../../auth/context'
import { useConversations } from '../../features/assistant/conversationsContext'
import { Icon, type IconName } from '../ui/Icon'

interface NavItem {
  label: string
  icon: IconName
}

interface NavLinkItem extends NavItem {
  to: string
}

const PRIMARY: NavLinkItem[] = [
  { label: 'New chat', icon: 'newChat', to: '/assistant' },
  { label: 'Dashboard', icon: 'dashboard', to: '/' },
  { label: 'Finance', icon: 'finance', to: '/finance' },
]

const COMING_SOON: NavItem[] = [
  { label: 'Study & Career', icon: 'study' },
  { label: 'Fitness', icon: 'fitness' },
  { label: 'Memory', icon: 'memory' },
  { label: 'Documents', icon: 'documents' },
  { label: 'Tasks', icon: 'tasks' },
]

const itemBase = 'flex h-10 items-center gap-3 rounded-lg px-2.5 text-sm no-underline'

interface SidebarProps {
  collapsed: boolean
  onToggle: () => void
}

function NavEntry({ item, collapsed }: { item: NavLinkItem; collapsed: boolean }) {
  return (
    <NavLink
      to={item.to}
      // Exact match: 'New chat' must not look active while an existing chat is open.
      end={item.to === '/' || item.to === '/assistant'}
      title={collapsed ? item.label : undefined}
      className={({ isActive }) =>
        `${itemBase} ${
          isActive
            ? 'bg-sidebar-active font-semibold text-sidebar-text'
            : 'font-medium text-sidebar-text hover:bg-sidebar-active/70'
        }`
      }
    >
      <Icon name={item.icon} />
      <span className={collapsed ? 'sr-only' : ''}>{item.label}</span>
    </NavLink>
  )
}

function ChatList() {
  const { conversations, loadError, remove } = useConversations()
  const { conversationId } = useParams()
  const navigate = useNavigate()

  async function handleDelete(id: string, title: string) {
    // Deleting is permanent, so confirm first.
    if (!window.confirm(`Delete "${title}"? This can't be undone.`)) return
    try {
      await remove(id)
      if (id === conversationId) navigate('/assistant')
    } catch {
      window.alert('Could not delete the conversation. Please try again.')
    }
  }

  let body
  if (loadError) body = <p className="m-0 px-2.5 text-xs text-sidebar-muted">Couldn't load chats.</p>
  else if (conversations === null) body = <p className="m-0 px-2.5 text-xs text-sidebar-muted">Loading…</p>
  else if (conversations.length === 0) body = <p className="m-0 px-2.5 text-xs text-sidebar-muted">No chats yet.</p>
  else
    body = (
      <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
        {conversations.map((c) => (
          <li key={c.id} className="group relative">
            <NavLink
              to={`/assistant/${c.id}`}
              title={c.title}
              className={({ isActive }) =>
                `flex h-9 items-center rounded-lg pr-9 pl-2.5 text-sm text-sidebar-text no-underline ${
                  isActive ? 'bg-sidebar-active font-medium' : 'hover:bg-sidebar-active/70'
                }`
              }
            >
              <span className="truncate">{c.title}</span>
            </NavLink>
            <button
              type="button"
              onClick={() => void handleDelete(c.id, c.title)}
              aria-label={`Delete chat: ${c.title}`}
              title="Delete chat"
              className="absolute top-0.5 right-0.5 flex size-8 cursor-pointer items-center justify-center rounded-md border-none bg-transparent text-sidebar-muted opacity-0 group-hover:opacity-100 hover:text-sidebar-text focus-visible:opacity-100"
            >
              <Icon name="trash" size={15} />
            </button>
          </li>
        ))}
      </ul>
    )

  return (
    <section aria-labelledby="chats-heading" className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto">
      <h2 id="chats-heading" className="m-0 px-2.5 pt-2 pb-1 text-xs font-medium text-sidebar-muted">
        Chats
      </h2>
      {body}
    </section>
  )
}

function initials(fullName: string): string {
  const parts = fullName.trim().split(/\s+/)
  return ((parts[0]?.[0] ?? '') + (parts.length > 1 ? (parts.at(-1)?.[0] ?? '') : '')).toUpperCase() || '?'
}

function AccountRow({ collapsed }: { collapsed: boolean }) {
  const user = useCurrentUser()
  const { logout } = useAuth()

  return (
    <div className={`flex items-center gap-2.5 px-1.5 py-2 ${collapsed ? 'flex-col' : ''}`}>
      <div
        aria-hidden="true"
        title={collapsed ? user.full_name : undefined}
        className="flex size-8 flex-none items-center justify-center rounded-full bg-accent text-xs font-semibold text-on-accent"
      >
        {initials(user.full_name)}
      </div>
      <div className={collapsed ? 'sr-only' : 'flex min-w-0 flex-1 flex-col'}>
        <span className="truncate text-sm font-semibold">{user.full_name}</span>
        <span className="truncate text-xs text-sidebar-muted">{user.email}</span>
      </div>
      <button
        type="button"
        onClick={() => void logout()}
        aria-label="Sign out"
        title="Sign out"
        className="flex size-8 flex-none cursor-pointer items-center justify-center rounded-lg border-none bg-transparent text-sidebar-muted hover:bg-sidebar-active hover:text-sidebar-text"
      >
        <Icon name="logout" size={16} />
      </button>
    </div>
  )
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  return (
    <nav
      aria-label="Main"
      className={`flex flex-none flex-col gap-4 border-r border-line bg-sidebar px-2.5 py-3 text-sidebar-text transition-[width] duration-200 ${
        collapsed ? 'w-15' : 'w-62'
      }`}
    >
      <div className={`flex h-10 items-center ${collapsed ? 'justify-center' : 'justify-between pl-2'}`}>
        {!collapsed && (
          <span className="flex items-center gap-2 font-semibold">
            <Icon name="logo" size={22} className="text-accent" />
            LifePilot
          </span>
        )}
        <button
          type="button"
          onClick={onToggle}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          aria-expanded={!collapsed}
          className="flex size-10 cursor-pointer items-center justify-center rounded-lg border-none bg-transparent text-sidebar-text hover:bg-sidebar-active"
        >
          <Icon name="panel" />
        </button>
      </div>

      <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
        {PRIMARY.map((item) => (
          <li key={item.label}>
            <NavEntry item={item} collapsed={collapsed} />
          </li>
        ))}
      </ul>

      <div className="flex flex-col gap-0.5">
        {!collapsed && <h2 className="m-0 px-2.5 pt-2 pb-1 text-xs font-medium text-sidebar-muted">Coming soon</h2>}
        <ul aria-label={collapsed ? 'Coming soon' : undefined} className="m-0 flex list-none flex-col gap-0.5 p-0">
          {COMING_SOON.map((item) => (
            <li
              key={item.label}
              title={collapsed ? `${item.label} (coming soon)` : undefined}
              className={`${itemBase} font-medium text-sidebar-muted`}
            >
              <Icon name={item.icon} />
              <span className={collapsed ? 'sr-only' : ''}>{item.label}</span>
            </li>
          ))}
        </ul>
      </div>

      {collapsed ? <div className="flex-1" /> : <ChatList />}

      <div className="flex flex-col gap-0.5 border-t border-line pt-2">
        <NavEntry item={{ label: 'Settings', icon: 'settings', to: '/settings' }} collapsed={collapsed} />
        <AccountRow collapsed={collapsed} />
      </div>
    </nav>
  )
}
