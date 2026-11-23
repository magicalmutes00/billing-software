/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#101828',
        muted: '#667085',
        line: '#e4e7ec',
        brand: {
          50: '#eef4ff',
          100: '#dbe8ff',
          500: '#3538cd',
          600: '#2731b8',
          700: '#222691',
        },
      },
      boxShadow: {
        card: '0 1px 2px rgba(16,24,40,.04), 0 8px 24px rgba(16,24,40,.04)',
      },
      borderRadius: { xl: '14px' },
    },
  },
  plugins: [],
};
