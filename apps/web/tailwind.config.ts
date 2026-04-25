import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        ink: "#112218",
        mist: "#eef5ec",
        moss: "#dce8d7",
        pine: "#214233",
        leaf: "#3f7d5e",
        amber: "#c7812f",
        rose: "#b84d4d",
        lake: "#3d7aa6",
        violet: "#6d5ca8"
      },
      boxShadow: {
        panel: "0 18px 40px rgba(18, 40, 29, 0.08)"
      },
      fontFamily: {
        sans: ["Inter", "Helvetica Neue", "sans-serif"],
        serif: ["Playfair Display", "Times New Roman", "serif"],
        body: ["Lora", "Georgia", "serif"],
        mono: ["JetBrains Mono", "Courier New", "monospace"]
      }
    }
  },
  plugins: []
};

export default config;
