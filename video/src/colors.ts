export const COLORS = {
  bg: "#0d1117",
  terminalBg: "#1e1e2e",
  terminalHeader: "#313244",
  text: "#cdd6f4",
  green: "#a6e3a1",
  blue: "#89b4fa",
  red: "#f38ba8",
  yellow: "#f9e2af",
  purple: "#cba6f7",
  teal: "#94e2d5",
  surface: "#181825",
  overlay: "#11111b",
  cursor: "#a6e3a1",
  dimText: "#6c7086",
  prompt: "#89b4fa",
  white: "#ffffff",
};

export const FPS = 30;

// Scene timings derived from actual audio durations + minimal visual buffer.
// Audio: 4.69 + 18.48 + 19.50 + 32.55 + 26.61 + 7.94 = 109.77s
// Each scene = ceil(audio) + 1–2s settle, CTA gets +5s for end card hold.
export const TITLE_CARD_DURATION = 2; // 2s static poster frame

export const TIMINGS = {
  hook: { start: TITLE_CARD_DURATION, duration: 6 }, // audio 4.69s
  context: { start: TITLE_CARD_DURATION + 6, duration: 20 }, // audio 18.48s
  act1: { start: TITLE_CARD_DURATION + 26, duration: 21 }, // audio 19.50s
  act2: { start: TITLE_CARD_DURATION + 47, duration: 34 }, // audio 32.55s
  act3: { start: TITLE_CARD_DURATION + 81, duration: 28 }, // audio 26.61s
  cta: { start: TITLE_CARD_DURATION + 109, duration: 13 }, // audio 7.94s + end card
} as const;

export const TOTAL_DURATION = TITLE_CARD_DURATION + 122; // 2:04
