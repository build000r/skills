import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { COLORS } from "../colors";
import { Terminal, PromptLine } from "../components/Terminal";

const COMMAND = "/trend-to-content";

const SEARCH_RESULTS = [
  {
    title: "Claude Code Skills Marketplace — Official Docs",
    url: "docs.anthropic.com/skills/marketplace",
    snippet: "Install community skills with npx skills add...",
  },
  {
    title: "Building Composable AI Workflows with Claude Skills",
    url: "dev.to/claude-skills-orchestration",
    snippet: "Chain multiple skills into automated pipelines...",
  },
  {
    title: "Skills vs Plugins: Why Claude's Approach Wins",
    url: "medium.com/ai-tooling/skills-vs-plugins",
    snippet: "The open-source, file-based approach lets developers...",
  },
  {
    title: "r/ClaudeAI — Has anyone chained skills together?",
    url: "reddit.com/r/ClaudeAI/comments/skills-chain",
    snippet: '"I got 3 skills to run in sequence and it felt like magic..."',
  },
];

const CONCEPT_LINES = [
  { text: "Video Concept Analysis:", color: COLORS.teal, bold: true },
  { text: "", color: COLORS.text, bold: false },
  {
    text: "  Content gap: Nobody is demoing skill orchestration",
    color: COLORS.text,
    bold: false,
  },
  {
    text: "  Angle: Self-referential — the video IS the demo",
    color: COLORS.white,
    bold: true,
  },
  {
    text: "  Format: Screen capture + TTS voiceover",
    color: COLORS.text,
    bold: false,
  },
  { text: "", color: COLORS.text, bold: false },
  {
    text: '  Title: "This Video Was Made by the Skills It\'s About"',
    color: COLORS.white,
    bold: true,
  },
  { text: "", color: COLORS.text, bold: false },
  { text: "  Why this works:", color: COLORS.text, bold: false },
  {
    text: "    ▸ Proves the workflow by showing it",
    color: COLORS.text,
    bold: false,
  },
  {
    text: "    ▸ Recursive hook creates curiosity",
    color: COLORS.text,
    bold: false,
  },
  {
    text: "    ▸ No need for external footage",
    color: COLORS.text,
    bold: false,
  },
  { text: "", color: COLORS.text, bold: false },
  {
    text: "  ✓ Recommended: Proceed with inception angle",
    color: COLORS.green,
    bold: true,
  },
];

/**
 * ACT 3: THE INCEPTION (28s = 840 frames)
 * Audio: 26.61s
 *
 * Narrator beats:
 *   0–3s:   "Here's where it gets recursive."
 *   3–8s:   "I invoke trend-to-content and ask it to research video angles..."
 *   8–14s:  "It searches for what's trending in the Claude Code skills space..."
 *   14–20s: "...finds that skills orchestration is the content gap..."
 *   20–25s: "...and recommends the exact concept you're watching right now."
 *   25–27s: "The script you're hearing? Written by the output of that workflow."
 *
 * Timeline:
 *   0–25:     type command
 *   30–60:    "Researching..." message
 *   60–90:    WebSearch query shows
 *   90–300:   search results slide in (4 × 1.5s stagger)
 *   240–600:  concept lines stream (14 lines over ~12s = 1.17 l/s)
 *   600–840:  "Recommended" highlighted, hold
 */
export const Act3Scene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Command
  const CMD_CPF = 0.55;
  const cmdChars = Math.min(
    COMMAND.length,
    Math.floor(Math.max(0, frame - 5) * CMD_CPF),
  );
  const cmdDone = cmdChars >= COMMAND.length;

  // Search results — staggered starting at 3s, every 1.5s
  const SEARCH_START = Math.round(fps * 3);
  const SEARCH_STAGGER = Math.round(fps * 1.5);

  // Concept output — starts at 8s, ~1.2 lines/sec
  const CONCEPT_START = Math.round(fps * 8);
  const CONCEPT_LPS = 1.2;
  const conceptCount = Math.floor(
    Math.max(0, frame - CONCEPT_START) * (CONCEPT_LPS / fps),
  );
  const visibleConcept = CONCEPT_LINES.slice(
    0,
    Math.min(CONCEPT_LINES.length, conceptCount),
  );

  const allConcept = conceptCount >= CONCEPT_LINES.length;
  const recommendedPulse = allConcept
    ? interpolate(frame % 50, [0, 25, 50], [1, 0.6, 1])
    : 1;

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg, padding: 60 }}>
      <div style={{ display: "flex", gap: 24, height: "100%" }}>
        {/* Terminal */}
        <div style={{ flex: 3 }}>
          <Terminal title="~/repos/skills — trend-to-content">
            <PromptLine>
              <span style={{ color: COLORS.green }}>
                {COMMAND.slice(0, cmdChars)}
                {!cmdDone && frame >= 5 && (
                  <span style={{ color: COLORS.cursor }}>▎</span>
                )}
              </span>
            </PromptLine>

            {cmdDone && (
              <div style={{ marginTop: 8 }}>
                <div style={{ color: COLORS.dimText }}>
                  Researching video angles for Claude Code skills...
                </div>
                {frame >= Math.round(fps * 2) && (
                  <div style={{ color: COLORS.blue, marginTop: 4 }}>
                    WebSearch: "claude code skills demo video 2026"
                  </div>
                )}
              </div>
            )}

            {/* Concept output */}
            {frame >= CONCEPT_START && (
              <div style={{ marginTop: 12 }}>
                {visibleConcept.map((line, i) => {
                  const isRec = line.text.includes("Recommended");
                  return (
                    <div
                      key={i}
                      style={{
                        color: line.color,
                        fontWeight: line.bold ? 700 : 400,
                        opacity: isRec ? recommendedPulse : 1,
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

        {/* Search results */}
        <div
          style={{
            flex: 2,
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}
        >
          {SEARCH_RESULTS.map((result, i) => {
            const rStart = SEARCH_START + i * SEARCH_STAGGER;
            if (frame < rStart) return null;

            const progress = spring({
              frame: frame - rStart,
              fps,
              config: { damping: 18, stiffness: 100 },
            });
            const opacity = interpolate(progress, [0, 0.4], [0, 1], {
              extrapolateRight: "clamp",
            });
            const tx = interpolate(progress, [0, 1], [30, 0]);

            return (
              <div
                key={result.url}
                style={{
                  backgroundColor: COLORS.surface,
                  border: `1px solid ${COLORS.terminalHeader}`,
                  borderRadius: 8,
                  padding: "14px 18px",
                  opacity,
                  transform: `translateX(${tx}px)`,
                }}
              >
                <div
                  style={{
                    fontFamily: "sans-serif",
                    fontSize: 11,
                    color: COLORS.dimText,
                    marginBottom: 4,
                  }}
                >
                  {result.url}
                </div>
                <div
                  style={{
                    fontFamily: "sans-serif",
                    fontSize: 16,
                    color: COLORS.blue,
                    fontWeight: 600,
                    marginBottom: 6,
                  }}
                >
                  {result.title}
                </div>
                <div
                  style={{
                    fontFamily: "sans-serif",
                    fontSize: 13,
                    color: COLORS.dimText,
                    lineHeight: 1.4,
                  }}
                >
                  {result.snippet}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};
