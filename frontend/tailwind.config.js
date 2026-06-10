/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        dark: {
          900: "#090A0F",
          800: "#0F111A",
          700: "#171A26",
          600: "#222638",
          500: "#2E334D"
        },
        gold: {
          500: "#E5A93B",
          600: "#C78E29",
          400: "#F1C268",
          300: "#FAD896"
        }
      }
    },
  },
  plugins: [],
}
