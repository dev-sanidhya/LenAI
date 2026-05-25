/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f0f4ff",
          100: "#dbe4ff",
          500: "#4361ee",
          600: "#3a56d4",
          700: "#2f4ab8",
          900: "#1a2a6b",
        },
      },
    },
  },
  plugins: [],
};
