import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#1B2522",
        panel: "#F5F7F8",
        line: "#E3EAE7",
        mute: "#5E706A",
        brand: "#00B386",
        gold: "#00B386",
        up: "#00B386",
        down: "#D64545",
      },
      fontFamily: {
        sans: ["Plus Jakarta Sans", "Segoe UI", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["Cascadia Mono", "ui-monospace", "SFMono-Regular", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
