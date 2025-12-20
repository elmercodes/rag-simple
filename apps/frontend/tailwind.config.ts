import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "rgb(var(--color-canvas) / <alpha-value>)",
        panel: "rgb(var(--color-panel) / <alpha-value>)",
        card: "rgb(var(--color-card) / <alpha-value>)",
        ink: "rgb(var(--color-ink) / <alpha-value>)",
        muted: "rgb(var(--color-muted) / <alpha-value>)",
        border: "rgb(var(--color-border) / <alpha-value>)",
        accent: "rgb(var(--color-accent) / <alpha-value>)",
        "accent-strong": "rgb(var(--color-accent-strong) / <alpha-value>)",
        "accent-contrast": "rgb(var(--color-accent-contrast) / <alpha-value>)",
        chip: "rgb(var(--color-chip) / <alpha-value>)",
        "chip-text": "rgb(var(--color-chip-text) / <alpha-value>)",
        "active-bg": "rgb(var(--color-active-bg) / <alpha-value>)",
        "active-text": "rgb(var(--color-active-text) / <alpha-value>)",
        "active-border": "rgb(var(--color-active-border) / <alpha-value>)",
        assistant: "rgb(var(--color-assistant) / <alpha-value>)",
        user: "rgb(var(--color-user) / <alpha-value>)"
      },
      boxShadow: {
        soft: "0 18px 45px -30px rgba(15, 23, 42, 0.35)",
        glow: "0 0 0 1px rgba(15, 23, 42, 0.08), 0 12px 25px -20px rgba(15, 23, 42, 0.5)"
      },
      fontFamily: {
        sans: ["var(--font-sans)"]
      }
    }
  },
  plugins: [require("@tailwindcss/typography")]
};

export default config;
