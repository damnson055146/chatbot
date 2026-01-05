import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { AssistantAvatar } from '../chat/AssistantAvatar'
import { ASSISTANT_AVATAR } from '../../utils/assistantProfile'
import {
  fetchAdminAssistantProfile,
  updateAdminAssistantProfile,
  uploadAdminAssistantAvatar,
  type AssistantAvatarPayload,
  type AdminAssistantProfileResponsePayload,
} from '../../services/apiClient'

type Draft = {
  name: string
  avatar: AssistantAvatarPayload
}

const emptyDraft = (): Draft => ({
  name: '',
  avatar: { ...ASSISTANT_AVATAR },
})

export function AssistantProfileManager({ readOnly = false }: { readOnly?: boolean }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [draft, setDraft] = useState<Draft>(emptyDraft)
  const [status, setStatus] = useState<{ tone: 'info' | 'error'; message: string } | null>(null)
  const [isUploading, setIsUploading] = useState(false)

  const profileQuery = useQuery<AdminAssistantProfileResponsePayload, Error>({
    queryKey: ['admin-assistant-profile'],
    queryFn: fetchAdminAssistantProfile,
    staleTime: 1000 * 30,
  })

  const updatedAt = useMemo(() => {
    const raw = profileQuery.data?.updated_at
    if (!raw) return null
    return new Date(raw).toLocaleString()
  }, [profileQuery.data?.updated_at])

  useEffect(() => {
    if (!profileQuery.data?.profile) return
    const profile = profileQuery.data.profile
    setDraft({
      name: profile.name ?? '',
      avatar: { ...ASSISTANT_AVATAR, ...profile.avatar },
    })
  }, [profileQuery.data])

  const applyProfile = (profile: AdminAssistantProfileResponsePayload['profile']) => {
    setDraft({
      name: profile.name ?? '',
      avatar: { ...ASSISTANT_AVATAR, ...profile.avatar },
    })
  }

  const updateDraft = (key: keyof AssistantAvatarPayload, value: string) => {
    setDraft((prev) => ({
      ...prev,
      avatar: { ...prev.avatar, [key]: value },
    }))
  }

  const handleSave = async () => {
    if (readOnly) return
    const name = draft.name.trim()
    if (!name) {
      setStatus({ tone: 'error', message: t('admin.profile.error.name_required') })
      return
    }
    setStatus(null)
    try {
      await updateAdminAssistantProfile({
        name,
        avatar: draft.avatar,
      })
      await queryClient.invalidateQueries({ queryKey: ['admin-assistant-profile'] })
      setStatus({ tone: 'info', message: t('admin.profile.status.saved') })
    } catch (error) {
      setStatus({
        tone: 'error',
        message: error instanceof Error ? error.message : t('admin.profile.error.save'),
      })
    }
  }

  const handleAvatarUpload = async (file: File) => {
    if (readOnly) return
    setStatus(null)
    setIsUploading(true)
    try {
      const response = await uploadAdminAssistantAvatar(file)
      if (response.profile) {
        applyProfile(response.profile)
      }
      await queryClient.invalidateQueries({ queryKey: ['admin-assistant-profile'] })
      await queryClient.invalidateQueries({ queryKey: ['assistant-profile'] })
      setStatus({ tone: 'info', message: t('admin.profile.status.saved') })
    } catch (error) {
      setStatus({
        tone: 'error',
        message: error instanceof Error ? error.message : t('admin.profile.error.save'),
      })
    } finally {
      setIsUploading(false)
    }
  }

  const handleRemoveAvatar = async () => {
    if (readOnly) return
    setStatus(null)
    try {
      const response = await updateAdminAssistantProfile({
        avatar: { image_url: null },
      })
      if (response.profile) {
        applyProfile(response.profile)
      }
      await queryClient.invalidateQueries({ queryKey: ['admin-assistant-profile'] })
      await queryClient.invalidateQueries({ queryKey: ['assistant-profile'] })
      setStatus({ tone: 'info', message: t('admin.profile.status.saved') })
    } catch (error) {
      setStatus({
        tone: 'error',
        message: error instanceof Error ? error.message : t('admin.profile.error.save'),
      })
    }
  }

  const handleRevert = () => {
    if (!profileQuery.data?.profile) return
    const profile = profileQuery.data.profile
    setDraft({
      name: profile.name ?? '',
      avatar: { ...ASSISTANT_AVATAR, ...profile.avatar },
    })
    setStatus(null)
  }

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold text-slate-900">{t('admin.profile.title')}</h3>
            <p className="mt-1 text-xs text-slate-500">{t('admin.profile.subtitle')}</p>
            {updatedAt ? (
              <p className="mt-2 text-xs text-slate-500">{t('admin.profile.updated_at', { time: updatedAt })}</p>
            ) : null}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-semibold text-slate-700 hover:border-slate-400"
              onClick={handleRevert}
              disabled={readOnly || profileQuery.isLoading}
            >
              {t('common.revert')}
            </button>
            <button
              type="button"
              className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs font-semibold text-slate-700 hover:border-slate-400 disabled:cursor-not-allowed disabled:opacity-50"
              onClick={handleSave}
              disabled={readOnly || profileQuery.isLoading}
            >
              {t('common.save')}
            </button>
          </div>
        </div>

        {profileQuery.error ? (
          <p className="mt-2 text-xs text-rose-600">{profileQuery.error.message}</p>
        ) : null}
        {status ? (
          <p className={`mt-2 text-xs ${status.tone === 'error' ? 'text-rose-600' : 'text-slate-500'}`}>{status.message}</p>
        ) : null}

        <div className="mt-6 grid gap-6 lg:grid-cols-[200px_1fr]">
          <div className="flex flex-col items-center gap-3 rounded-2xl border border-slate-200 bg-slate-50 px-4 py-6">
            <AssistantAvatar size={72} showHalo avatar={draft.avatar} />
            <p className="text-xs font-semibold text-slate-600">{draft.name || t('assistant.name')}</p>
            <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
              <button
                type="button"
                className="rounded-full border border-slate-300 bg-white px-3 py-1 text-[11px] font-semibold text-slate-700 hover:border-slate-400 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={() => fileInputRef.current?.click()}
                disabled={readOnly || profileQuery.isLoading || isUploading}
              >
                {t('admin.profile.avatar_upload')}
              </button>
              {draft.avatar.image_url ? (
                <button
                  type="button"
                  className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[11px] font-semibold text-slate-600 hover:border-slate-300 disabled:cursor-not-allowed disabled:opacity-50"
                  onClick={() => void handleRemoveAvatar()}
                  disabled={readOnly || profileQuery.isLoading || isUploading}
                >
                  {t('admin.profile.avatar_remove')}
                </button>
              ) : null}
            </div>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t('admin.profile.field.name')}>
              <input
                value={draft.name}
                onChange={(event) => setDraft((prev) => ({ ...prev, name: event.target.value }))}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
                disabled={readOnly || profileQuery.isLoading}
              />
            </Field>
            <div className="sm:col-span-2">
              <p className="text-xs font-semibold uppercase tracking-[0.35em] text-slate-400">{t('admin.profile.avatar_title')}</p>
            </div>
            <Field label={t('admin.profile.field.avatar_accent')}>
              <AvatarInput
                value={draft.avatar.accent}
                onChange={(value) => updateDraft('accent', value)}
                disabled={readOnly || profileQuery.isLoading}
              />
            </Field>
            <Field label={t('admin.profile.field.avatar_base')}>
              <AvatarInput
                value={draft.avatar.base}
                onChange={(value) => updateDraft('base', value)}
                disabled={readOnly || profileQuery.isLoading}
              />
            </Field>
            <Field label={t('admin.profile.field.avatar_ring')}>
              <AvatarInput
                value={draft.avatar.ring}
                onChange={(value) => updateDraft('ring', value)}
                disabled={readOnly || profileQuery.isLoading}
              />
            </Field>
            <Field label={t('admin.profile.field.avatar_face')}>
              <AvatarInput
                value={draft.avatar.face}
                onChange={(value) => updateDraft('face', value)}
                disabled={readOnly || profileQuery.isLoading}
              />
            </Field>
          </div>
        </div>
      </div>
      <input
        ref={fileInputRef}
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0]
          if (file) {
            void handleAvatarUpload(file)
          }
          event.target.value = ''
        }}
      />
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block text-sm text-slate-700">
      <span className="text-xs uppercase tracking-wide text-slate-500">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  )
}

function AvatarInput({
  value,
  onChange,
  disabled,
}: {
  value: string
  onChange: (value: string) => void
  disabled: boolean
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="h-9 w-9 rounded-full border border-slate-200" style={{ backgroundColor: value }} />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
        disabled={disabled}
      />
    </div>
  )
}

export default AssistantProfileManager
