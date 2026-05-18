/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        matrix: {
          'dark': '#000a00',
          'deep': '#001200',
          'green': '#00ff41',
          'bright': '#00ff88',
          'dim': '#003300',
          'glow': '#00ff4180',
          'faint': '#00330040',
        }
      },
      fontFamily: {
        'mono-matrix': ['"Share Tech Mono"', 'monospace'],
        'orbitron': ['Orbitron', 'sans-serif'],
        'rajdhani': ['Rajdhani', 'sans-serif'],
      },
      animation: {
        'glow-pulse': 'glow-pulse 2s ease-in-out infinite',
        'scan-line': 'scan-line 8s linear infinite',
        'text-flicker': 'text-flicker 3s linear infinite',
        'fade-in-up': 'fade-in-up 1s ease-out forwards',
        'glitch': 'glitch 2s infinite',
      },
      keyframes: {
        'glow-pulse': {
          '0%, 100%': { textShadow: '0 0 10px #00ff41, 0 0 20px #00ff41, 0 0 40px #00ff41' },
          '50%': { textShadow: '0 0 5px #00ff41, 0 0 10px #00ff41, 0 0 20px #00ff41' },
        },
        'scan-line': {
          '0%': { transform: 'translateY(-100%)' },
          '100%': { transform: 'translateY(100vh)' },
        },
        'text-flicker': {
          '0%, 19.999%, 22%, 62.999%, 64%, 64.999%, 70%, 100%': { opacity: '1' },
          '20%, 21.999%, 63%, 63.999%, 65%, 69.999%': { opacity: '0.33' },
        },
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(30px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'glitch': {
          '0%': { textShadow: '2px 0 #00ff41, -2px 0 #ff0040' },
          '2%': { textShadow: '-2px 0 #00ff41, 2px 0 #ff0040' },
          '4%': { textShadow: '2px 0 #00ff41, -2px 0 #ff0040' },
          '6%': { textShadow: '0px 0 #00ff41' },
          '100%': { textShadow: '0px 0 #00ff41' },
        },
      },
    },
  },
  plugins: [],
}
