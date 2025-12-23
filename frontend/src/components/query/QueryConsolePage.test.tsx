import type { ReactElement } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'

import { QueryConsolePage } from './QueryConsolePage'

const mockPostQuery = vi.fn()
const mockFetchActiveSessions = vi.fn()
const mockFetchSessionState = vi.fn()
const mockUploadAttachment = vi.fn()
const mockDeleteSession = vi.fn()

vi.mock('../../services/apiClient', () => ({
  postQuery: (...args: unknown[]) => mockPostQuery(...args),
  fetchActiveSessions: (...args: unknown[]) => mockFetchActiveSessions(...args),
  fetchSessionState: (...args: unknown[]) => mockFetchSessionState(...args),
  uploadAttachment: (...args: unknown[]) => mockUploadAttachment(...args),
  deleteSession: (...args: unknown[]) => mockDeleteSession(...args),
}))

function renderWithClient(ui: ReactElement) {
  const queryClient = new QueryClient()
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

describe('QueryConsolePage', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
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
    mockUploadAttachment.mockResolvedValue({
      upload_id: 'upload-1',
      filename: 'file.pdf',
      mime_type: 'application/pdf',
      size_bytes: 1234,
      sha256: 'abc',
      stored_at: new Date().toISOString(),
      download_url: 'http://localhost/uploads/file.pdf',
    })
    mockDeleteSession.mockResolvedValue(undefined)
  })

  it('renders ChatGPT-inspired shell with navigation and composer', () => {
    renderWithClient(<QueryConsolePage />)
    expect(screen.getAllByText(/Study Abroad Assistant/i).length).toBeGreaterThan(0)
    expect(screen.getByRole('button', { name: /New chat/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/Message composer/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Send message/i })).toBeInTheDocument()
  })

  it('sends a user prompt and renders assistant reply', async () => {
    renderWithClient(<QueryConsolePage />)
    const textarea = screen.getByLabelText(/Message composer/i)
    fireEvent.change(textarea, { target: { value: 'Test question about visas' } })
    fireEvent.click(screen.getByRole('button', { name: /Send message/i }))

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
      slot_suggestions: ['I want to study in Australia'],
    })

    renderWithClient(<QueryConsolePage />)
    const textarea = screen.getByLabelText(/Message composer/i)
    fireEvent.change(textarea, { target: { value: 'Help me plan' } })
    fireEvent.click(screen.getByRole('button', { name: /Send message/i }))

    await waitFor(() => expect(screen.getByText(/Slot guidance/i)).toBeInTheDocument())
    expect(screen.getByText(/target_country/i)).toBeInTheDocument()
    expect(screen.getByText(/Which country are you hoping to study in\?/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Use/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /I want to study in Australia/i })).toBeInTheDocument()
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

    fireEvent.click(screen.getByRole('button', { name: /Settings/i }))

    await waitFor(() => expect(screen.getByText(/User settings/i)).toBeInTheDocument())
    expect(screen.getAllByDisplayValue('Chinese')[0]).toHaveValue('zh')
    expect(screen.getByLabelText(/Explain like new/i)).toHaveDisplayValue('On by default')
  })
})
