import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";
import { COLORS } from "../colors";
import { Terminal, PromptLine } from "../components/Terminal";
import { CaptionBadgeStack } from "../components/CaptionBadge";

const COMMAND = "/skill-issue";

const OUTPUT_LINES = [
  { text: "Scanning 4 skills...", color: COLORS.dimText },
  { text: "", color: COLORS.dimText },
  { text: "skill-issue/", color: COLORS.purple },
  { text: "  ✗ nested duplicate directory", color: COLORS.red },
  { text: "  ✗ bare except: on line 219", color: COLORS.red },
  { text: "  ✗ missing license file", color: COLORS.yellow },
  { text: "", color: COLORS.dimText },
  { text: "divide-and-conquer/", color: COLORS.blue },
  { text: "  ✗ duplicated hook formulas", color: COLORS.red },
  { text: "  ✗ missing license file", color: COLORS.yellow },
  { text: "", color: COLORS.dimText },
  { text: "trend-to-content/", color: COLORS.teal },
  { text: "  ✗ no root README", color: COLORS.red },
  { text: "  ✗ inconsistent packaging", color: COLORS.yellow },
  { text: "  ✗ missing license file", color: COLORS.yellow },
  { text: "", color: COLORS.dimText },
  { text: "prompt-reviewer/", color: COLORS.yellow },
  { text: "  ✗ nested duplicate directory", color: COLORS.red },
  { text: "  ✗ missing license file", color: COLORS.yellow },
  { text: "  ✗ unused dependencies", color: COLORS.yellow },
  { text: "", color: COLORS.dimText },
  { text: "Found 12 issues across 4 skills", color: COLORS.white },
];

const ISSUE_LABELS = [
  { text: "nested duplicate directory", color: COLORS.red },
  { text: "bare except: on line 219", color: COLORS.red },
  { text: "missing licenses", color: COLORS.yellow },
  { text: "duplicated hook formulas", color: COLORS.red },
  { text: "no root README", color: COLORS.red },
];

/**
 * ACT 1: SKILL-ISSUE (21s = 630 frames)
 * Audio: 19.50s
 *
 * Narrator beats:
 *   0–4s:   "First, I ask skill-issue to review every skill in this directory."
 *   4–12s:  "It found 12 issues across all 4 skills. Real problems — not lint
 *            noise. Structural duplication, missing licenses, inconsistent
 *            packaging."
 *   12–19s: "Now I need to fix all of them. But they're spread across
 *            4 different directories."
 *
 * Timeline:
 *   0–25:     type "/skill-issue" fast (~0.8s)
 *   30–45:    "Scanning..." appears
 *   45–360:   output streams (22 lines over ~10.5s = 2.1 lines/sec)
 *   120–420:  badges stagger in (5 × 60f = every 2s, synced to narrator)
 *   360–630:  summary highlighted, hold to end
 */
export const Act1Scene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Command typing — fast, ~0.8s
  const CMD_CPF = 0.6;
  const cmdChars = Math.min(
    COMMAND.length,
    Math.floor(Math.max(0, frame - 5) * CMD_CPF),
  );
  const cmdDone = cmdChars >= COMMAND.length;

  // Output stream — starts at 1.5s, 2.1 lines/sec
  const OUT_START = Math.round(fps * 1.5);
  const LINES_PER_SEC = 2.1;
  const visibleCount = Math.floor(
    Math.max(0, frame - OUT_START) * (LINES_PER_SEC / fps),
  );
  const visibleLines = OUTPUT_LINES.slice(
    0,
    Math.min(OUTPUT_LINES.length, visibleCount),
  );

  // Caption badges — start at 4s, stagger every 1.5s (synced to narrator listing issues)
  const BADGE_START = Math.round(fps * 4);
  const BADGE_STAGGER = Math.round(fps * 1.5);

  // Summary line glow
  const allOutput = visibleCount >= OUTPUT_LINES.length;
  const summaryGlow = allOutput
    ? interpolate(frame % 50, [0, 25, 50], [1, 0.6, 1])
    : 1;

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg, padding: 60 }}>
      <div style={{ display: "flex", gap: 24, height: "100%" }}>
        <div style={{ flex: 2 }}>
          <Terminal title="~/repos/skills — skill-issue">
            <PromptLine>
              <span style={{ color: COLORS.green }}>
                {COMMAND.slice(0, cmdChars)}
                {!cmdDone && frame >= 5 && (
                  <span style={{ color: COLORS.cursor }}>▎</span>
                )}
              </span>
            </PromptLine>
            {cmdDone && (
              <div style={{ marginTop: 12 }}>
                {visibleLines.map((line, i) => {
                  const isLast =
                    i === OUTPUT_LINES.length - 1 && allOutput;
                  return (
                    <div
                      key={i}
                      style={{
                        color: line.color,
                        opacity: isLast ? summaryGlow : 1,
                        fontWeight: isLast ? 700 : 400,
                      }}
                    >
                      {line.text || "\u00A0"}
                    </div>
                  );
                })}
              </div>
            )}
          </Terminal>
        </div>

        <div style={{ flex: 1, position: "relative" }}>
          <CaptionBadgeStack
            labels={ISSUE_LABELS}
            startFrame={BADGE_START}
            stagger={BADGE_STAGGER}
          />
        </div>
      </div>
    </AbsoluteFill>
  );
};
