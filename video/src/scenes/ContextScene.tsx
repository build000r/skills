import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { COLORS } from "../colors";
import { Terminal, PromptLine, OutputLine } from "../components/Terminal";

const SKILL_DIRS = [
  { name: "skill-issue/", color: COLORS.purple },
  { name: "divide-and-conquer/", color: COLORS.blue },
  { name: "trend-to-content/", color: COLORS.teal },
  { name: "prompt-reviewer/", color: COLORS.yellow },
];

const FRONTMATTERS = [
  {
    name: "skill-issue",
    desc: "Review and audit Claude Code skills",
    color: COLORS.purple,
  },
  {
    name: "divide-and-conquer",
    desc: "Parallelize work across independent agents",
    color: COLORS.blue,
  },
  {
    name: "trend-to-content",
    desc: "Turn research into content at scale",
    color: COLORS.teal,
  },
];

/**
 * CONTEXT (20s = 600 frames)
 * Audio: 18.48s
 *
 * Narrator (estimated beats):
 *   0–6s:  "This repo has 4 Claude Code skills. Three of them chain
 *           together into a single workflow..."
 *   6–15s: "skill-issue reviews skills. divide-and-conquer parallelizes
 *           work. trend-to-content turns research into content."
 *   15–18s: "Let's run them."
 *
 * Timeline:
 *   0–15:     ls typed instantly
 *   8–60:     directories pop in (stagger 8f each)
 *   60–180:   hold terminal while narrator explains
 *   150–270:  card 1 (skill-issue) — synced to narrator naming it
 *   270–390:  card 2 (divide-and-conquer)
 *   390–510:  card 3 (trend-to-content)
 *   510–600:  return to terminal prompt, settle
 */
export const ContextScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // ls is typed near-instantly
  const lsTyped = frame >= 8;
  const showOutput = frame >= 20;

  // Frontmatter cards
  const CARD_START = Math.round(fps * 5); // 150 — when narrator names first skill
  const CARD_DUR = Math.round(fps * 4); // 120 frames = 4s per card

  // Active card index (-1 = none)
  const activeCard = Math.floor(
    Math.max(0, frame - CARD_START) / CARD_DUR,
  );
  const showCards = frame >= CARD_START && activeCard < FRONTMATTERS.length;

  // After all cards: return to terminal with prompt
  const postCards = frame >= CARD_START + CARD_DUR * FRONTMATTERS.length;

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg, padding: 60 }}>
      {/* Terminal (visible when cards aren't showing, or post-cards) */}
      <div
        style={{
          position: "absolute",
          inset: 60,
          opacity: showCards && !postCards ? 0 : 1,
        }}
      >
        <Terminal title="~/repos/skills">
          <PromptLine>
            <span style={{ color: COLORS.green }}>
              {lsTyped ? "ls" : "l"}
              {!lsTyped && <span style={{ color: COLORS.cursor }}>▎</span>}
            </span>
          </PromptLine>
          {showOutput && (
            <div style={{ marginTop: 12 }}>
              {SKILL_DIRS.map((dir, i) => {
                const appear = 20 + i * 8;
                const o = interpolate(frame, [appear, appear + 6], [0, 1], {
                  extrapolateLeft: "clamp",
                  extrapolateRight: "clamp",
                });
                return (
                  <OutputLine key={dir.name} color={dir.color}>
                    <span style={{ opacity: o }}>{dir.name}</span>
                  </OutputLine>
                );
              })}
              <OutputLine color={COLORS.dimText}>
                <span
                  style={{
                    opacity: interpolate(frame, [55, 65], [0, 1], {
                      extrapolateLeft: "clamp",
                      extrapolateRight: "clamp",
                    }),
                  }}
                >
                  SKILL.md &nbsp; README.md &nbsp; video-script.md
                </span>
              </OutputLine>
            </div>
          )}
          {postCards && (
            <div style={{ marginTop: 24 }}>
              <PromptLine>
                <span
                  style={{
                    color: COLORS.dimText,
                    opacity: interpolate(
                      frame % 24,
                      [0, 12, 24],
                      [1, 0, 1],
                    ),
                  }}
                >
                  ▎
                </span>
              </PromptLine>
            </div>
          )}
        </Terminal>
      </div>

      {/* Frontmatter cards */}
      {showCards &&
        (() => {
          const fm = FRONTMATTERS[activeCard];
          if (!fm) return null;
          const cardLocalFrame = frame - (CARD_START + activeCard * CARD_DUR);

          const enterProgress = spring({
            frame: cardLocalFrame,
            fps,
            config: { damping: 18, stiffness: 120 },
          });
          const exitProgress = interpolate(
            cardLocalFrame,
            [CARD_DUR - 10, CARD_DUR],
            [1, 0],
            { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
          );

          return (
            <AbsoluteFill
              style={{
                justifyContent: "center",
                alignItems: "center",
                opacity: Math.min(enterProgress, exitProgress),
                transform: `scale(${interpolate(enterProgress, [0, 1], [0.96, 1])})`,
              }}
            >
              <div
                style={{
                  backgroundColor: COLORS.surface,
                  border: `2px solid ${fm.color}`,
                  borderRadius: 16,
                  padding: "48px 64px",
                  maxWidth: 900,
                  fontFamily: '"JetBrains Mono", monospace',
                }}
              >
                <div
                  style={{
                    fontSize: 14,
                    color: COLORS.dimText,
                    marginBottom: 8,
                    letterSpacing: 1,
                  }}
                >
                  SKILL.md
                </div>
                <div
                  style={{ fontSize: 36, color: fm.color, fontWeight: 700 }}
                >
                  {fm.name}
                </div>
                <div
                  style={{
                    fontSize: 22,
                    color: COLORS.text,
                    marginTop: 16,
                    lineHeight: 1.5,
                  }}
                >
                  {fm.desc}
                </div>
              </div>
            </AbsoluteFill>
          );
        })()}
    </AbsoluteFill>
  );
};
