/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        "border-emphasis": "hsl(var(--border-emphasis))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        elevated: "hsl(var(--elevated))",
        subtle: "hsl(var(--subtle-foreground))",

        /* Interactive + semantic tokens — the single source for meaning. */
        brand: {
          DEFAULT: "hsl(var(--brand))",
          foreground: "hsl(var(--brand-foreground))",
        },
        success: "hsl(var(--success))",
        warning: "hsl(var(--warning))",
        danger: "hsl(var(--danger))",
        agent: "hsl(var(--agent))",

        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
      },
      borderRadius: {
        "2xl": "1.125rem",
        xl: "0.875rem",
        lg: "0.5rem",
        md: "0.375rem",
        sm: "0.25rem",
      },
      keyframes: {
        "feed-in": {
          "0%": {
            opacity: "0",
            transform: "translateY(-6px)",
            backgroundColor: "hsl(217 91% 60% / 0.14)",
          },
          "60%": { opacity: "1", backgroundColor: "hsl(217 91% 60% / 0.09)" },
          "100%": { backgroundColor: "transparent" },
        },
      },
      animation: {
        "feed-in": "feed-in 2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
