import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { COLORS } from "../colors";

const INSTALL_COMMANDS = [
  "npx skills add build000r/skill-issue",
  "npx skills add build000r/divide-and-conquer",
  "npx skills add build000r/trend-to-content",
  "npx skills add build000r/prompt-reviewer",
];

/**
 * CTA (13s = 390 frames)
 * Audio: 7.94s — then end card holds.
 *
 * Narrator beats:
 *   0–4s:  "All 4 skills are open source and work with any Claude Code project."
 *   4–7s:  "Star the repo. Install a skill. Build something recursive."
 *
 * Timeline:
 *   0–10:    first command starts typing
 *   10–180:  all 4 commands appear (stagger ~1s = 30f, typing at 1.0 c/f)
 *   240–270: transition to end card
 *   270–390: end card holds
 */
export const CtaScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const END_CARD_START = Math.round(fps * 8);
  const showEndCard = frame >= END_CARD_START;

  const endCardIn = showEndCard
    ? spring({
        frame: frame - END_CARD_START,
        fps,
        config: { damping: 18, stiffness: 80 },
      })
    : 0;

  const CMD_STAGGER = fps; // 30f = 1s between lines
  const CMD_CPF = 1.0; // fast typing

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg }}>
      {/* Install commands */}
      <AbsoluteFill
        style={{
          justifyContent: "center",
          alignItems: "center",
          opacity: showEndCard ? 1 - endCardIn : 1,
          transform: showEndCard
            ? `scale(${interpolate(endCardIn, [0, 1], [1, 0.95])})`
            : undefined,
        }}
      >
        <div
          style={{
            backgroundColor: COLORS.terminalBg,
            borderRadius: 16,
            border: `1px solid ${COLORS.terminalHeader}`,
            padding: "48px 64px",
            display: "flex",
            flexDirection: "column",
            gap: 18,
          }}
        >
          {INSTALL_COMMANDS.map((cmd, i) => {
            const lineStart = 10 + i * CMD_STAGGER;
            if (frame < lineStart) return null;

            const elapsed = frame - lineStart;
            const chars = Math.min(cmd.length, Math.floor(elapsed * CMD_CPF));
            const done = chars >= cmd.length;

            const lineIn = spring({
              frame: elapsed,
              fps,
              config: { damping: 20, stiffness: 120 },
            });

            return (
              <div
                key={cmd}
                style={{
                  fontFamily: '"JetBrains Mono", monospace',
                  fontSize: 24,
                  opacity: interpolate(lineIn, [0, 0.3], [0, 1], {
                    extrapolateRight: "clamp",
                  }),
                  display: "flex",
                  gap: 10,
                }}
              >
                <span style={{ color: COLORS.prompt }}>$</span>
                <span style={{ color: COLORS.green }}>
                  {cmd.slice(0, chars)}
                </span>
                {!done && (
                  <span style={{ color: COLORS.cursor }}>▎</span>
                )}
              </div>
            );
          })}
        </div>
      </AbsoluteFill>

      {/* End card */}
      {showEndCard && (
        <AbsoluteFill
          style={{
            justifyContent: "center",
            alignItems: "center",
            opacity: endCardIn,
          }}
        >
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: 32,
            }}
          >
            <div
              style={{
                fontFamily: '"JetBrains Mono", monospace',
                fontSize: 48,
                fontWeight: 700,
                color: COLORS.white,
                letterSpacing: -1,
              }}
            >
              github.com/
              <span style={{ color: COLORS.green }}>build000r</span>
              /skills
            </div>

            <div
              style={{
                fontFamily: "sans-serif",
                fontSize: 22,
                color: COLORS.dimText,
                letterSpacing: 2,
              }}
            >
              OPEN SOURCE &middot; CLAUDE CODE SKILLS
            </div>

            <div
              style={{
                marginTop: 16,
                display: "flex",
                gap: 12,
                alignItems: "center",
                fontFamily: '"JetBrains Mono", monospace',
                fontSize: 18,
                color: COLORS.yellow,
                opacity: interpolate(
                  spring({
                    frame: frame - END_CARD_START - Math.round(fps * 0.5),
                    fps,
                    config: { damping: 15, stiffness: 80 },
                  }),
                  [0, 1],
                  [0, 1],
                ),
              }}
            >
              <span style={{ fontSize: 24 }}>&#9733;</span>
              Star the repo. Install a skill. Build something recursive.
            </div>
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
};
