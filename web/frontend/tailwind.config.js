/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#1B4F72',
          light: '#2471A3',
          dark: '#154360',
        },
        success: {
          DEFAULT: '#27AE60',
          light: '#2ECC71',
          dark: '#1E8449',
        },
        danger: {
          DEFAULT: '#E74C3C',
          light: '#EC7063',
          dark: '#CB4335',
        },
        warning: {
          DEFAULT: '#F39C12',
          light: '#F5B041',
          dark: '#D68910',
        },
        background: '#ECF0F1',
        dark: {
          DEFAULT: '#2C3E50',
          light: '#34495E',
          lighter: '#5D6D7E',
        },
      },
      minWidth: {
        touch: '48px',
      },
      minHeight: {
        touch: '48px',
      },
    },
  },
  plugins: [],
};
