/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: '#1D4ED8',
          secondary: '#F59E0B',
        },
      },
    },
  },
  plugins: [],
}
