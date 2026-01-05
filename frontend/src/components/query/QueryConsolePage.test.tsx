import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'

import '../../utils/i18n'
import { QueryConsolePage } from './QueryConsolePage'

let queryClient: QueryClient | null = null

const mockPostQuery = vi.fn()
const mockFetchActiveSessions = vi.fn()
const mockFetchSessionState = vi.fn()
const mockUploadAttachment = vi.fn()
const mockDeleteSession = vi.fn()
const mockFetchSlotCatalog = vi.fn()
const mockIngestUploadUser = vi.fn()
const mockStreamQuery = vi.fn()
const mockUpdateSessionSlots = vi.fn()
const mockCreateSession = vi.fn()
const mockUpdateSessionMetadata = vi.fn()
const mockFetchSessionMessages = vi.fn()
const mockAuthMe = vi.fn()
const mockAuthLogout = vi.fn()
const mockGetAccessToken = vi.fn()
const mockClearAccessToken = vi.fn()
const mockFetchUserProfile = vi.fn()
const mockUpdateUserProfile = vi.fn()
const mockCreateEscalation = vi.fn()

vi.mock('../../services/apiClient', () => ({
  authMe: (...args: unknown[]) => mockAuthMe(...args),
  authLogout: (...args: unknown[]) => mockAuthLogout(...args),
  getAccessToken: (...args: unknown[]) => mockGetAccessToken(...args),
  clearAccessToken: (...args: unknown[]) => mockClearAccessToken(...args),
  fetchUserProfile: (...args: unknown[]) => mockFetchUserProfile(...args),
  updateUserProfile: (...args: unknown[]) => mockUpdateUserProfile(...args),
  postQuery: (...args: unknown[]) => mockPostQuery(...args),
  fetchActiveSessions: (...args: unknown[]) => mockFetchActiveSessions(...args),
  fetchSessionState: (...args: unknown[]) => mockFetchSessionState(...args),
  createSession: (...args: unknown[]) => mockCreateSession(...args),
  updateSessionMetadata: (...args: unknown[]) => mockUpdateSessionMetadata(...args),
  fetchSessionMessages: (...args: unknown[]) => mockFetchSessionMessages(...args),
  fetchSlotCatalog: (...args: unknown[]) => mockFetchSlotCatalog(...args),
  ingestUploadUser: (...args: unknown[]) => mockIngestUploadUser(...args),
  streamQuery: (...args: unknown[]) => mockStreamQuery(...args),
  uploadAttachment: (...args: unknown[]) => mockUploadAttachment(...args),
  deleteSession: (...args: unknown[]) => mockDeleteSession(...args),
  updateSessionSlots: (...args: unknown[]) => mockUpdateSessionSlots(...args),
  createEscalation: (...args: unknown[]) => mockCreateEscalation(...args),
  fetchChunkDetail: () =>
    Promise.resolve({
      chunk: {
        chunk_id: 'mock-chunk',
        doc_id: 'mock-doc',
        text: 'Mock chunk text',
        last_verified_at: null,
        highlights: [],
        metadata: {},
      },
    }),
}))

function renderWithClient(ui: ReactElement) {
  queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: Infinity,
      },
    },
  })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('QueryConsolePage', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    mockGetAccessToken.mockReturnValue(null)
    mockAuthMe.mockResolvedValue({ sub: 'user-1', role: 'user', token_type: 'Bearer' })
    mockAuthLogout.mockResolvedValue(undefined)
    mockFetchUserProfile.mockResolvedValue({
      display_name: null,
      contact_email: null,
      updated_at: new Date().toISOString(),
    })
    mockUpdateUserProfile.mockResolvedValue({
      display_name: null,
      contact_email: null,
      updated_at: new Date().toISOString(),
    })
    mockCreateEscalation.mockResolvedValue({
      escalation_id: 'esc-1',
      status: 'pending',
      created_at: new Date().toISOString(),
      session_id: 'mock-session',
      message_id: 'msg-1',
    })
    mockPostQuery.mockResolvedValue({
      answer: 'Mock answer',
      citations: [],
      session_id: 'mock-session',
      slots: {},
      diagnostics: null,
      missing_slots: [],
      slot_prompts: {},
      slot_errors: {},
      slot_suggestions: [],
    })
    mockFetchActiveSessions.mockResolvedValue([])
    mockFetchSessionState.mockResolvedValue({
      session_id: 'mock-session',
      slots: {},
      slot_errors: {},
      language: 'auto',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      remaining_ttl_seconds: null,
      slot_count: 0,
    })
    mockCreateSession.mockResolvedValue({
      session_id: 'mock-session',
      slots: {},
      slot_errors: {},
      language: 'auto',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      remaining_ttl_seconds: null,
      slot_count: 0,
    })
    mockUpdateSessionMetadata.mockResolvedValue({
      session_id: 'mock-session',
      slots: {},
      slot_errors: {},
      language: 'auto',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      remaining_ttl_seconds: null,
      slot_count: 0,
    })
    mockFetchSessionMessages.mockResolvedValue([])
    mockUploadAttachment.mockResolvedValue({
      upload_id: 'upload-1',
      filename: 'file.pdf',
      mime_type: 'application/pdf',
      size_bytes: 1234,
      sha256: 'abc',
      stored_at: new Date().toISOString(),
      download_url: 'http://localhost/uploads/file.pdf',
    })
    mockFetchSlotCatalog.mockResolvedValue([])
    mockIngestUploadUser.mockResolvedValue({
      doc_id: 'mock-doc',
      version: 1,
      chunk_count: 0,
      health: {
        document_count: 0,
        chunk_count: 0,
      },
    })
    mockStreamQuery.mockResolvedValue({
      answer: 'Mock stream answer',
      citations: [],
      session_id: 'mock-session',
      slots: {},
      diagnostics: null,
      missing_slots: [],
      slot_prompts: {},
      slot_errors: {},
      slot_suggestions: [],
    })
    mockUpdateSessionSlots.mockResolvedValue({
      session_id: 'mock-session',
      slots: {},
      slot_errors: {},
      language: 'auto',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      remaining_ttl_seconds: null,
      slot_count: 0,
    })
    mockDeleteSession.mockResolvedValue(undefined)
  })

  afterEach(() => {
    queryClient?.clear()
    queryClient = null
  })

  const waitForInitialLoad = async () => {
    await waitFor(() => expect(mockFetchActiveSessions).toHaveBeenCalled())
  }

  it('renders ChatGPT-inspired shell with navigation and composer', async () => {
    renderWithClient(<QueryConsolePage />)
    await waitForInitialLoad()
    expect(mockCreateSession).not.toHaveBeenCalled()
    expect(screen.getAllByText(/Study Abroad Assistant/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /New chat/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/Message composer/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Send message/i })).toBeInTheDocument()
  })

  it('sends a user prompt and renders assistant reply', async () => {
    renderWithClient(<QueryConsolePage />)
    await waitForInitialLoad()
    const textarea = screen.getByLabelText(/Message composer/i)
    fireEvent.change(textarea, { target: { value: 'Test question about visas' } })
    fireEvent.click(screen.getByRole('button', { name: /Send message/i }))

    await waitFor(() => expect(mockCreateSession).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText(/Mock answer/i)).toBeInTheDocument())
    expect(screen.getAllByText(/Test question about visas/i).length).toBeGreaterThan(0)
    expect(mockPostQuery).toHaveBeenCalledWith(expect.objectContaining({ question: 'Test question about visas' }))
  })

  it('renders slot guidance when backend returns missing slots', async () => {
    mockPostQuery.mockResolvedValueOnce({
      answer: 'I need more info',
      citations: [],
      session_id: 'mock-session',
      slots: {},
      diagnostics: null,
      missing_slots: ['target_country'],
      slot_prompts: { target_country: 'Which country are you hoping to study in?' },
      slot_errors: {},
      slot_suggestions: [
        'I want to study in Australia. Can you suggest suitable programs?',
        'What is the typical visa timeline for Australian student visas?',
        'How much should I budget annually for a master\'s in Australia?',
      ],
    })

    renderWithClient(<QueryConsolePage />)
    await waitForInitialLoad()
    const textarea = screen.getByLabelText(/Message composer/i)
    fireEvent.change(textarea, { target: { value: 'Help me plan' } })
    fireEvent.click(screen.getByRole('button', { name: /Send message/i }))

    await waitFor(() => expect(mockCreateSession).toHaveBeenCalled())
    await waitFor(() => expect(screen.getByText(/Slot guidance/i)).toBeInTheDocument())
    expect(screen.getAllByText(/target_country/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Which country are you hoping to study in\?/i).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: /^Use$/i }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: /I want to study in Australia/i }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: /visa timeline/i }).length).toBeGreaterThan(0)
    expect(screen.getAllByRole('button', { name: /budget annually/i }).length).toBeGreaterThan(0)
  })

  it('honors stored preferences within the settings drawer', async () => {
    localStorage.setItem(
      'rag.user.preferences',
      JSON.stringify({
        displayName: 'Test Analyst',
        avatarColor: '#000000',
        preferredLanguage: 'zh',
        explainLikeNewDefault: true,
        defaultTopK: 5,
        defaultKCite: 4,
        retentionDays: 60,
        theme: 'high-contrast',
      }),
    )

    renderWithClient(<QueryConsolePage />)
    await waitForInitialLoad()

    const settingsButton = screen.getByText('Settings').closest('button')
    expect(settingsButton).toBeTruthy()
    fireEvent.click(settingsButton as HTMLButtonElement)

    await waitFor(() => expect(screen.getByText(/User settings/i)).toBeInTheDocument())
    expect(screen.getAllByDisplayValue('Chinese')[0]).toHaveValue('zh')
    expect(screen.getByLabelText(/Explain like new/i)).toHaveDisplayValue('On by default')
  })
})
