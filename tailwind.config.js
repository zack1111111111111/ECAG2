/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        cream: "#F7F7F7",
        ink: "#0B0B0B",
        muted: "#5F6368",
        mint: "#D9F2C7",
        aqua: "#BFEFF4",
        butter: "#FFE680",
        cloud: "#F0F1EF",
      },
      boxShadow: {
        soft: "0 24px 70px rgba(28, 32, 30, 0.08)",
        lift: "0 18px 42px rgba(28, 32, 30, 0.10)",
      },
      borderRadius: {
        "4xl": "2rem",
        "5xl": "2.5rem",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "sans-serif",
        ],
      },
    },
  },
  plugins: [],
};
