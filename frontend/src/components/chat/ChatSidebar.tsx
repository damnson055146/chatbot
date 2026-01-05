import { useMemo, useState, type MouseEvent } from 'react'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import type { ConversationSummary } from './types'

interface ChatSidebarProps {
  conversations: ConversationSummary[]
  activeSessionId?: string
  searchTerm: string
  onSearchChange: (value: string) => void
  onSelect: (sessionId: string) => void
  onCreateNew: () => void
  onTogglePin: (sessionId: string) => void
  onRenameRequest: (conversation: ConversationSummary) => void
  onArchiveToggle: (sessionId: string) => void
  showArchived: boolean
  onToggleArchivedVisibility: () => void
  isLoading: boolean
  onSettings: () => void
  onWorkspaceNavigate?: (key: string) => void
  onSystemNavigate?: (key: string) => void
  onDelete: (sessionId: string) => void
  onCollapseToggle?: () => void
  showAdminConsole?: boolean
}

const NAV_ITEMS: Array<{ key: string; icon: string }> = [{ key: 'nav.chat', icon: '💬' }]

const SYSTEM_ITEMS: Array<{ key: string; icon: string }> = [{ key: 'nav.admin_console', icon: '🛠️' }]

const formatRelativeTime = (t: (key: string, opts?: any) => string, iso?: string) => {
  if (!iso) return t('time.moments_ago')
  const diff = Date.now() - new Date(iso).getTime()
  const minutes = Math.max(1, Math.round(diff / 60000))
  if (minutes < 60) return t('time.minutes_ago', { count: minutes })
  const hours = Math.round(minutes / 60)
  if (hours < 24) return t('time.hours_ago', { count: hours })
  const days = Math.round(hours / 24)
  return t('time.days_ago', { count: days })
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
  onRenameRequest,
  onArchiveToggle,
  showArchived,
  onToggleArchivedVisibility,
  isLoading,
  onSettings,
  onWorkspaceNavigate,
  onSystemNavigate,
  onDelete,
  onCollapseToggle,
  showAdminConsole = true,
}: ChatSidebarProps) {
  const location = useLocation()
  const { t } = useTranslation()
  const [actionMenuId, setActionMenuId] = useState<string | null>(null)
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
    onRenameRequest(conversation)
  }

  const activeWorkspace = 'nav.chat'

  const activeSystem = useMemo(() => {
    const path = location.pathname
    if (path.startsWith('/admin')) return 'nav.admin_console'
    return null
  }, [location.pathname])
  const systemItems = showAdminConsole ? SYSTEM_ITEMS : []

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
                    <p className="truncate">{conversation.title || t('sidebar.untitled_conversation')}</p>
                    <p className={`mt-1 text-xs ${metaColor}`}>{formatRelativeTime(t, conversation.updatedAt)}</p>
                  </div>
                  <div className="relative">
                    <button
                      type="button"
                      aria-label={t('sidebar.actions_label')}
                      className="rounded-full border border-transparent px-2 py-1 text-lg leading-none text-slate-500 hover:border-slate-300"
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
                          {t('sidebar.action.rename')}
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
                          {conversation.pinned ? t('sidebar.action.unpin') : t('sidebar.action.pin')}
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
                          {conversation.archived ? t('sidebar.action.restore') : t('sidebar.action.archive')}
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
                          {t('sidebar.action.delete')}
                        </button>
                      </div>
                    ) : null}
                  </div>
                </div>
                <p className={`mt-2 text-xs ${metaColor}`}>{t('sidebar.slots_count', { count: conversation.slotCount })}</p>
              </div>
            </li>
          )
        })}
      </ul>
    )
  }

  const renderPinned = () => {
    if (pinnedList.length === 0) {
      return (
        <p className="mt-3 rounded-2xl border border-dashed border-slate-200 bg-white px-4 py-4 text-sm text-slate-400">
          {t('sidebar.no_pinned')}
        </p>
      )
    }
    return renderConversationList(pinnedList)
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto overscroll-contain border-r border-slate-200 bg-[#F8F8FA] px-4 pb-6 pt-4 text-slate-900">
      <div className="flex items-center justify-between rounded-3xl bg-white/80 px-4 py-3 shadow-sm">
        <div>
          <p className="text-sm font-semibold">{t('sidebar.study_abroad')}</p>
          <p className="text-xs text-slate-400">{t('sidebar.assistant_console')}</p>
        </div>
        <div className="flex items-center gap-2">
          {onCollapseToggle ? (
            <button
              type="button"
              aria-label={t('sidebar.collapse_sidebar')}
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
            {t('sidebar.new_chat')}
          </button>
        </div>
      </div>

      <section className="mt-6">
        <p className={sectionTitleClass}>{t('sidebar.workspace')}</p>
        <div className="mt-3 space-y-2">
          {NAV_ITEMS.map((item) => (
            <NavButton
              key={item.key}
              label={t(item.key)}
              icon={item.icon}
              active={item.key === activeWorkspace}
              onClick={() => onWorkspaceNavigate?.(item.key)}
            />
          ))}
        </div>
      </section>

      {systemItems.length > 0 ? (
        <section className="mt-6">
          <p className={`${sectionTitleClass} opacity-80`}>{t('sidebar.system')}</p>
          <div className="mt-3 space-y-2">
            {systemItems.map((item) => (
              <NavButton
                key={item.key}
                label={t(item.key)}
                icon={item.icon}
                active={item.key === activeSystem}
                onClick={() => onSystemNavigate?.(item.key)}
              />
            ))}
          </div>
        </section>
      ) : null}

      <section className="mt-6">
        <div className="relative">
          <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-300">🔍</span>
          <input
            type="search"
            value={searchTerm}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder={t('sidebar.search_conversations_placeholder')}
            className="w-full rounded-[999px] border border-slate-200 bg-white py-2 pl-10 pr-4 text-sm text-slate-700 shadow-inner focus:border-slate-400 focus:outline-none"
          />
        </div>

        <div className="mt-6 flex items-center justify-between">
          <span className={sectionTitleClass}>{t('sidebar.pinned')}</span>
          <button
            type="button"
            className={`rounded-full px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.3em] ${
              archivedList.length === 0 ? 'cursor-not-allowed border border-slate-100 text-slate-300' : 'border border-slate-200 text-slate-500 hover:border-slate-300'
            }`}
            onClick={onToggleArchivedVisibility}
            disabled={archivedList.length === 0}
          >
            {showArchived ? t('common.hide') : `${t('sidebar.archived')} (${archivedList.length})`}
          </button>
        </div>
        <div className="mt-4 space-y-3">
          {renderPinned()}
          {showArchived && archivedList.length > 0 ? (
            <div>
              <p className="mt-6 text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">{t('sidebar.archived')}</p>
              <div className="mt-3">{renderConversationList(archivedList)}</div>
            </div>
          ) : null}
        </div>
      </section>

      <section className="mt-6">
        <p className={sectionTitleClass}>{t('sidebar.conversations')}</p>
        <div className="mt-4">
          {isLoading ? (
            <div className="rounded-3xl border border-dashed border-slate-200 bg-white/70 px-4 py-6 text-center text-sm text-slate-500">
              {t('common.loading')}
            </div>
          ) : conversations.length === 0 ? (
            <div className="rounded-3xl border border-dashed border-slate-200 bg-white/70 px-4 py-6 text-center text-sm text-slate-500">
              {t('sidebar.no_conversations')}
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
          {t('sidebar.settings')}
          <span className="text-xs text-slate-400">⌘ ,</span>
        </button>
      </div>
    </div>
  )
}

export default ChatSidebar

function NavButton({
  label,
  icon,
  active,
  muted,
  onClick,
}: {
  label: string
  icon: string
  active: boolean
  muted?: boolean
  onClick?: () => void
}) {
  return (
    <button
      type="button"
      className={`flex w-full items-center justify-between rounded-xl px-4 py-3 text-left text-sm transition ${
        active ? 'bg-slate-900 text-white' : 'bg-transparent text-slate-700 hover:bg-white/70'
      } ${muted ? 'opacity-80' : ''}`}
      onClick={onClick}
    >
      <span className="flex items-center gap-2">
        <span aria-hidden="true">{icon}</span>
        <span className="font-semibold">{label}</span>
      </span>
      <span className={`text-xs ${active ? 'text-white/70' : 'text-slate-400'}`}>›</span>
    </button>
  )
}
