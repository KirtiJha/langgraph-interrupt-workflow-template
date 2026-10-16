/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        paper: "rgb(var(--paper) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        ember: {
          50: "#fff7ed",
          100: "#ffedd5",
          200: "#fed7aa",
          300: "#fdba74",
          400: "#fb923c",
          500: "#f97316",
          600: "#ea580c",
          700: "#c2410c",
          800: "#9a3412",
          900: "#7c2d12",
        },
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
        display: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      animation: {
        "fade-in": "fadeIn 0.4s ease-out",
        "slide-up": "slideUp 0.35s cubic-bezier(.2,.8,.2,1)",
        "slide-in": "slideIn 0.35s cubic-bezier(.2,.8,.2,1)",
        "pulse-soft": "pulseSoft 1.6s ease-in-out infinite",
        pop: "pop 0.3s cubic-bezier(.2,.8,.2,1)",
        shimmer: "shimmer 1.4s linear infinite",
      },
      keyframes: {
        fadeIn: { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideUp: { "0%": { transform: "translateY(12px)", opacity: "0" }, "100%": { transform: "translateY(0)", opacity: "1" } },
        slideIn: { "0%": { transform: "translateX(16px)", opacity: "0" }, "100%": { transform: "translateX(0)", opacity: "1" } },
        pulseSoft: { "0%, 100%": { opacity: "1" }, "50%": { opacity: "0.55" } },
        pop: { "0%": { transform: "scale(.96)", opacity: "0" }, "100%": { transform: "scale(1)", opacity: "1" } },
        shimmer: { "0%": { backgroundPosition: "-200% 0" }, "100%": { backgroundPosition: "200% 0" } },
      },
      boxShadow: {
        card: "0 1px 2px rgba(28,25,23,.04), 0 8px 24px -12px rgba(28,25,23,.12)",
        lift: "0 12px 40px -12px rgba(28,25,23,.25)",
      },
    },
  },
  plugins: [],
};
