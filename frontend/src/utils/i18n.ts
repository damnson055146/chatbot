import i18next from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from '../locales/en.json'
import zh from '../locales/zh.json'

const DEFAULT_LANGUAGE = import.meta.env.VITE_DEFAULT_LANGUAGE ?? 'en'

void i18next
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      zh: { translation: zh },
    },
    lng: DEFAULT_LANGUAGE,
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false,
    },
  })

export { i18next }
