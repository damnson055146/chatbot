export interface AssistantProfileHighlight {
  title: string
  description: string
  prompt: string
}

export interface AssistantProfileConfig {
  name: string
  title: string
  tagline: string
  avatar: {
    accent: string
    base: string
    ring: string
    face: string
  }
  highlights: AssistantProfileHighlight[]
  openingStatements: string[]
}

export const ASSISTANT_PROFILE: AssistantProfileConfig = {
  name: 'Lumi',
  title: 'Study Abroad Copilot',
  tagline: 'Planning visas, admissions, and scholarships with calm clarity.',
  avatar: {
    accent: '#2563eb',
    base: '#e0f2ff',
    ring: '#bfdbfe',
    face: '#0f172a',
  },
  highlights: [
    {
      title: 'Visa readiness scan',
      description: 'I can walk you through interview prep, wait times, and documents in one go.',
      prompt: 'Help me review my visa readiness for an upcoming interview.',
    },
    {
      title: 'Application roadmap',
      description: 'Let’s map deadlines across shortlists so nothing slips through.',
      prompt: 'Build a simple application roadmap for my top universities.',
    },
    {
      title: 'Funding leads',
      description: 'Share scholarships or assistantships that match my background.',
      prompt: 'Suggest scholarships or assistantships for an international engineering student.',
    },
  ],
  openingStatements: [
    'I keep a running log of embassy wait times and scholarship drops so you get answers that reflect this week’s reality.',
    'I condense policy updates from immigration offices so your plan is grounded in what officers are enforcing now.',
    'I pair every suggestion with the paperwork it impacts so you never wonder what to prepare next.',
    'My briefings each morning cover visas, admissions, and funding so you can confidently focus on the decision that’s due today.',
  ],
}

const timeSegments: Array<{ label: string; start: number; end: number }> = [
  { label: 'Good morning', start: 5, end: 11 },
  { label: 'Good afternoon', start: 11, end: 17 },
  { label: 'Good evening', start: 17, end: 22 },
]

export const getAssistantGreeting = (referenceDate = new Date()): string => {
  const hour = referenceDate.getHours()
  const segment = timeSegments.find((slot) => hour >= slot.start && hour < slot.end)
  return segment?.label ?? 'Hello'
}

export const getAssistantOpeningStatement = (referenceDate = new Date()): string => {
  const statements = ASSISTANT_PROFILE.openingStatements
  if (!statements.length) return ''
  const index = referenceDate.getDate() % statements.length
  return statements[index]
}
