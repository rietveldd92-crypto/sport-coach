/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        raised: "var(--bg-raised)",
        elevated: "var(--bg-elevated)",
        line: "var(--border)",
        "line-strong": "var(--border-strong)",
        ink: "var(--text)",
        muted: "var(--text-muted)",
        dim: "var(--text-dim)",
        accent: {
          DEFAULT: "var(--accent)",
          hover: "var(--accent-hover)",
        },
        positive: "var(--positive)",
        warning: "var(--warning)",
        alert: "var(--alert)",
        z1: "var(--zone-z1)",
        z2: "var(--zone-z2)",
        tempo: "var(--zone-tempo)",
        drempel: "var(--zone-drempel)",
        race: "var(--zone-race)",
      },
      fontFamily: {
        display: ["'Fraunces Variable'", "Georgia", "serif"],
        body: ["'Inter Variable'", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono Variable'", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
