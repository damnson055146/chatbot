import { ASSISTANT_PROFILE } from '../../utils/assistantProfile'

interface AssistantAvatarProps {
  size?: number
  className?: string
  showHalo?: boolean
}

export function AssistantAvatar({ size = 40, className = '', showHalo = false }: AssistantAvatarProps) {
  const dimension = `${size}px`
  const haloOffset = 8

  return (
    <div
      className={`relative flex items-center justify-center rounded-full shadow-sm ${className}`}
      style={{
        width: dimension,
        height: dimension,
        background: `linear-gradient(145deg, #ffffff, ${ASSISTANT_PROFILE.avatar.base})`,
      }}
      aria-hidden="true"
    >
      {showHalo ? (
        <span
          className="pointer-events-none absolute rounded-full"
          style={{
            inset: `-${haloOffset / 2}px`,
            boxShadow: `0 0 0 3px ${ASSISTANT_PROFILE.avatar.ring}55`,
            zIndex: 0,
          }}
        />
      ) : null}
      <div
        className="relative flex items-center justify-center rounded-full"
        style={{
          width: `calc(${dimension} - 8px)`,
          height: `calc(${dimension} - 8px)`,
          background: `linear-gradient(145deg, #ffffff, ${ASSISTANT_PROFILE.avatar.base})`,
          border: `2px solid ${ASSISTANT_PROFILE.avatar.ring}`,
          zIndex: 1,
        }}
      >
        <svg
          viewBox="0 0 64 64"
          className="text-slate-700"
          width={size - 16}
          height={size - 16}
          aria-hidden="true"
        >
          <rect x="12" y="18" width="40" height="28" rx="14" fill="white" stroke={ASSISTANT_PROFILE.avatar.accent} strokeWidth="3" />
          <circle cx="26" cy="32" r="5" fill={ASSISTANT_PROFILE.avatar.face} />
          <circle cx="38" cy="32" r="5" fill={ASSISTANT_PROFILE.avatar.face} />
          <path d="M24 42c4 4 12 4 16 0" stroke={ASSISTANT_PROFILE.avatar.accent} strokeWidth="3" strokeLinecap="round" />
          <path d="M18 20l-4-6" stroke={ASSISTANT_PROFILE.avatar.accent} strokeWidth="3" strokeLinecap="round" />
          <path d="M46 20l4-6" stroke={ASSISTANT_PROFILE.avatar.accent} strokeWidth="3" strokeLinecap="round" />
        </svg>
      </div>
    </div>
  )
}

export default AssistantAvatar
