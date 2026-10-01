import type { Config } from "tailwindcss";

// Design tokens - see docs/design-notes.md for the reasoning behind these
// choices (subject: Kenyan commercial livestock operation; signature motif:
// the ear-tag chip used everywhere an animal_number appears).
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: "#F7F3EA",      // warm bone background - not the #F4F1EA cliché
        ink: "#201F1B",        // near-black warm charcoal, primary text
        forest: {
          DEFAULT: "#1F3A2E",  // deep bottle-green - highland pasture, not SaaS blue
          dark: "#16281F",
          light: "#2C4F3E",
        },
        brass: {
          DEFAULT: "#B8862B",  // dry-season grass / brass ear-tag - the accent
          dark: "#936920",
          light: "#D9A84C",
        },
        clay: "#A6432E",       // muted brick red for errors - distinct from brass
        moss: "#3F6B4A",       // success
        hairline: "#E4DCC8",   // warm border color
        muted: "#8A8578",
      },
      fontFamily: {
        display: ["var(--font-fraunces)", "serif"],
        body: ["var(--font-plex-sans)", "sans-serif"],
        mono: ["var(--font-plex-mono)", "monospace"],
      },
      borderRadius: {
        tag: "4px",
      },
    },
  },
  plugins: [],
};
export default config;
