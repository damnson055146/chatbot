import { useState, type MouseEvent } from 'react'
import type { ConversationSummary } from './types'

interface ChatSidebarProps {
  conversations: ConversationSummary[]
  activeSessionId?: string
  searchTerm: string
  onSearchChange: (value: string) => void
  onSelect: (sessionId: string) => void
  onCreateNew: () => void
  onTogglePin: (sessionId: string) => void
  onRename: (sessionId: string, nextTitle: string) => void
  onArchiveToggle: (sessionId: string) => void
  showArchived: boolean
  onToggleArchivedVisibility: () => void
  isLoading: boolean
  onSettings: () => void
  onWorkspaceNavigate?: (label: string) => void
  onSystemNavigate?: (label: string) => void
  onDelete: (sessionId: string) => void
  onCollapseToggle?: () => void
}

const NAV_ITEMS = [
  { label: 'Chat', icon: '💬' },
  { label: 'Library', icon: '📚' },
  { label: 'Explore', icon: '🧭' },
]

const SYSTEM_ITEMS = [
  { label: 'System status', icon: '🩺' },
  { label: 'Metrics', icon: '📈' },
  { label: 'Sources', icon: '🗂️' },
  { label: 'Audit log', icon: '🧾' },
  { label: 'Admin console', icon: '🛠️' },
  { label: 'Release notes', icon: '🗒️' },
]

const formatRelativeTime = (iso?: string) => {
  if (!iso) return 'moments ago'
  const diff = Date.now() - new Date(iso).getTime()
  const minutes = Math.max(1, Math.round(diff / 60000))
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}

const sectionTitleClass = 'text-[11px] font-semibold uppercase tracking-[0.45em] text-slate-400'
export function ChatSidebar({
  conversations,
  activeSessionId,
  searchTerm,
  onSearchChange,
  onSelect,
  onCreateNew,
  onTogglePin,
  onRename,
  onArchiveToggle,
  showArchived,
  onToggleArchivedVisibility,
  isLoading,
  onSettings,
  onWorkspaceNavigate,
  onSystemNavigate,
  onDelete,
  onCollapseToggle,
}: ChatSidebarProps) {
  const [actionMenuId, setActionMenuId] = useState<string | null>(null)
  const [workspaceMenuOpen, setWorkspaceMenuOpen] = useState(true)
  const [systemMenuOpen, setSystemMenuOpen] = useState(false)
  const normalizedSearch = searchTerm.trim().toLowerCase()
  const filtered = normalizedSearch
    ? conversations.filter((conversation) => conversation.title.toLowerCase().includes(normalizedSearch))
    : conversations

  const archivedList = filtered.filter((conversation) => conversation.archived)
  const activeList = filtered.filter((conversation) => !conversation.archived)
  const pinnedList = activeList.filter((conversation) => conversation.pinned)
  const regularList = activeList.filter((conversation) => !conversation.pinned)

  const handleRename = (conversation: ConversationSummary, event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation()
    const nextTitle = window.prompt('Rename conversation', conversation.title)
    if (nextTitle === null) return
    onRename(conversation.sessionId, nextTitle.trim())
  }

const renderNavSection = (
  title: string,
  items: typeof NAV_ITEMS,
  handler?: (label: string) => void,
  muted = false,
  isOpen = false,
  onToggle?: () => void,
) => (
  <section className="mt-6">
    <div className="flex items-center justify-between">
      <p className={`${sectionTitleClass} ${muted ? 'opacity-70' : ''}`}>{title}</p>
      <button
        type="button"
        aria-label={`${title} menu`}
        className="rounded-full border border-slate-200 px-2 py-1 text-xs text-slate-500 transition hover:border-slate-300"
        onClick={onToggle}
      >
        ⋯
      </button>
    </div>
    {isOpen ? (
      <div className="mt-3 rounded-2xl border border-slate-200 bg-white shadow-sm">
        <ul className="divide-y divide-slate-100 text-sm text-slate-700">
          {items.map((item) => (
            <li key={item.label}>
              <button
                type="button"
                className="flex w-full items-center gap-2 px-4 py-2 text-left hover:bg-slate-50"
                onClick={() => handler?.(item.label)}
              >
                <span>{item.icon}</span>
                <span>{item.label}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>
    ) : null}
  </section>
)

  const renderConversationList = (items: ConversationSummary[]) => {
    if (items.length === 0) return null
    return (
      <ul className="space-y-3">
        {items.map((conversation) => {
          const isActive = conversation.sessionId === activeSessionId
          const baseClass =
            'relative rounded-3xl border px-4 py-4 text-left shadow-sm transition focus:outline-none focus:ring-2 focus:ring-slate-200'
          const activeClass = isActive
            ? 'border-slate-900 bg-white text-slate-900'
            : 'border-slate-200 bg-white text-slate-900 hover:border-slate-300'
          const metaColor = isActive ? 'text-slate-600' : 'text-slate-500'
          const isMenuOpen = actionMenuId === conversation.sessionId
          return (
            <li key={conversation.sessionId}>
              <div
                role="button"
                tabIndex={0}
                className={`${baseClass} ${activeClass}`}
                onClick={() => onSelect(conversation.sessionId)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault()
                    onSelect(conversation.sessionId)
                  }
                }}
              >
                <div className="flex items-start justify-between gap-3 text-sm font-semibold">
                  <div className="min-w-0 flex-1">
                    <p className="truncate">{conversation.title || 'Untitled conversation'}</p>
                    <p className={`mt-1 text-xs ${metaColor}`}>{formatRelativeTime(conversation.updatedAt)}</p>
                  </div>
                  <div className="relative">
                    <button
                      type="button"
                      aria-label="Conversation actions"
                      className={`rounded-full border border-transparent px-2 py-1 text-lg leading-none ${
                        isActive ? 'text-white hover:border-white/40' : 'text-slate-500 hover:border-slate-300'
                      }`}
                      onClick={(event) => {
                        event.stopPropagation()
                        setActionMenuId(isMenuOpen ? null : conversation.sessionId)
                      }}
                    >
                      ⋯
                    </button>
                    {isMenuOpen ? (
                      <div
                        className={`absolute right-0 top-8 z-30 w-44 rounded-2xl border px-2 py-2 text-sm shadow-lg ${
                          isActive ? 'border-slate-900 bg-white text-slate-900' : 'border-slate-200 bg-white text-slate-900'
                        }`}
                      >
                        <button
                          type="button"
                          className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-xs uppercase tracking-wide"
                          onClick={(event) => {
                            handleRename(conversation, event)
                            setActionMenuId(null)
                          }}
                        >
                          Rename
                        </button>
                        <button
                          type="button"
                          className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-xs uppercase tracking-wide"
                          onClick={(event) => {
                            event.stopPropagation()
                            onTogglePin(conversation.sessionId)
                            setActionMenuId(null)
                          }}
                        >
                          {conversation.pinned ? 'Unpin' : 'Pin'}
                        </button>
                        <button
                          type="button"
                          className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-xs uppercase tracking-wide"
                          onClick={(event) => {
                            event.stopPropagation()
                            onArchiveToggle(conversation.sessionId)
                            setActionMenuId(null)
                          }}
                        >
                          {conversation.archived ? 'Restore' : 'Archive'}
                        </button>
                        <button
                          type="button"
                          className="flex w-full items-center justify-between rounded-xl px-3 py-2 text-xs uppercase tracking-wide text-rose-500"
                          onClick={(event) => {
                            event.stopPropagation()
                            onDelete(conversation.sessionId)
                            setActionMenuId(null)
                          }}
                        >
                          Delete
                        </button>
                      </div>
                    ) : null}
                  </div>
                </div>
                <p className={`mt-2 text-xs ${metaColor}`}>
                  {conversation.slotCount} slot{conversation.slotCount === 1 ? '' : 's'}
                </p>
              </div>
            </li>
          )
        })}
      </ul>
    )
  }

  const renderPinned = () => {
    if (pinnedList.length === 0) {
      return <p className="mt-3 rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-4 text-sm text-slate-400">No pinned conversations yet.</p>
    }
    return renderConversationList(pinnedList)
  }

  return (
    <div className="flex h-full flex-col border-r border-slate-200 bg-[#F8F8FA] px-4 pb-6 pt-4 text-slate-900">
      <div className="flex items-center justify-between rounded-3xl bg-white/80 px-4 py-3 shadow-sm">
        <div>
          <p className="text-sm font-semibold">Study Abroad</p>
          <p className="text-xs text-slate-400">Assistant Console</p>
        </div>
        <div className="flex items-center gap-2">
          {onCollapseToggle ? (
            <button
              type="button"
              aria-label="Collapse sidebar"
              className="rounded-full border border-slate-200 px-2 py-1 text-xs text-slate-500 transition hover:border-slate-300"
              onClick={onCollapseToggle}
            >
              ⟨
            </button>
          ) : null}
          <button
            type="button"
            className="rounded-full border border-slate-200 px-3 py-1 text-xs font-semibold text-slate-600 transition hover:border-slate-300"
            onClick={onCreateNew}
          >
            + New chat
          </button>
        </div>
      </div>

      {renderNavSection(
        'Workspace',
        NAV_ITEMS,
        onWorkspaceNavigate,
        false,
        workspaceMenuOpen,
        () => setWorkspaceMenuOpen((prev) => !prev),
      )}
      {renderNavSection(
        'System menu',
        SYSTEM_ITEMS,
        onSystemNavigate,
        true,
        systemMenuOpen,
        () => setSystemMenuOpen((prev) => !prev),
      )}

      <section className="mt-6">
        <div className="relative">
          <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-300">🔍</span>
          <input
            type="search"
            value={searchTerm}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search conversations"
            className="w-full rounded-[999px] border border-slate-200 bg-white py-2 pl-10 pr-4 text-sm text-slate-700 shadow-inner focus:border-slate-400 focus:outline-none"
          />
        </div>

        <div className="mt-6 flex items-center justify-between">
          <span className={sectionTitleClass}>Pinned</span>
          <button
            type="button"
            className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.3em] ${
              archivedList.length === 0 ? 'cursor-not-allowed border border-slate-100 text-slate-300' : 'border border-slate-200 text-slate-500 hover:border-slate-300'
            }`}
            onClick={onToggleArchivedVisibility}
            disabled={archivedList.length === 0}
          >
            {showArchived ? 'Hide' : `Archived (${archivedList.length})`}
          </button>
        </div>
        <div className="mt-4 space-y-3">
          {renderPinned()}
          {showArchived && archivedList.length > 0 ? (
            <div>
              <p className="mt-6 text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">Archived</p>
              <div className="mt-3">{renderConversationList(archivedList)}</div>
            </div>
          ) : null}
        </div>
      </section>

      <section className="mt-6 flex-1 overflow-y-auto">
        <p className={sectionTitleClass}>Conversations</p>
        <div className="mt-4">
          {isLoading ? (
            <div className="rounded-3xl border border-dashed border-slate-200 bg-white/70 px-4 py-6 text-center text-sm text-slate-500">
              Loading conversations…
            </div>
          ) : conversations.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-slate-200 bg-white/70 px-4 py-6 text-center text-sm text-slate-500">
              No saved conversations yet.
            </div>
          ) : (
            renderConversationList(regularList)
          )}
        </div>
      </section>

      <div className="mt-6">
        <button
          type="button"
          onClick={onSettings}
          className="flex w-full items-center justify-between rounded-3xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-slate-300"
        >
          Settings
          <span className="text-xs text-slate-400">⌘ ,</span>
        </button>
      </div>
    </div>
  )
}

export default ChatSidebar
