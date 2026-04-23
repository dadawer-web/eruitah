/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        'geek-bg': '#0a0a0a',
        'geek-surface': '#111111',
        'geek-border': '#1e1e1e',
        'geek-accent': '#00ff88',
        'geek-accent-dim': '#00cc6a',
        'geek-text': '#d4d4d4',
        'geek-text-dim': '#737373',
      },
    },
  },
  plugins: [],
}
