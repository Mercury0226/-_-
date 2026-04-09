/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}', './UJMCanvas.jsx'],
  theme: {
    extend: {
      colors: {
        ink: '#13212e',
        sand: '#f6f4ef',
        ember: '#d64933',
        teal: '#1f8a70',
      },
      fontFamily: {
        display: ['Space Grotesk', 'Noto Sans SC', 'sans-serif'],
      },
      boxShadow: {
        soft: '0 12px 30px rgba(19, 33, 46, 0.12)',
      },
    },
  },
  plugins: [],
};
