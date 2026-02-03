import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
  Sequence,
} from "remotion";
import { COLORS } from "../colors";
import { Terminal, PromptLine } from "../components/Terminal";
import { AgentPanel } from "../components/AgentPanel";

const COMMAND = "/divide-and-conquer";

const PLAN_LINES = [
  "Analyzing 12 issues across 4 directories...",
  "",
  "Decomposition Plan:",
  "  Agent 1: skill-issue/       (3 issues)",
  "  Agent 2: divide-and-conquer/ (2 issues)",
  "  Agent 3: trend-to-content/   (3 issues)",
  "  Agent 4: prompt-reviewer/    (4 issues)",
  "",
  "Conflict Check:",
  "  Write overlap:    0 files",
  "  Data dependencies: 0",
  "  Status: SAFE — launching all 4 agents",
];

const AGENTS = [
  {
    title: "Agent 1: skill-issue",
    lines: [
      "Reading SKILL.md...",
      "Removing nested duplicate/",
      "  rm -rf skill-issue/skill-issue/",
      "Fixing bare except (line 219)",
      "  except Exception as e:",
      "Creating LICENSE (MIT)",
      "All 3 issues resolved.",
    ],
  },
  {
    title: "Agent 2: divide-and-conquer",
    lines: [
      "Reading SKILL.md...",
      "Deduplicating hook formulas",
      "  extracted to shared/hooks.py",
      "  updated 3 references",
      "Creating LICENSE (MIT)",
      "All 2 issues resolved.",
    ],
  },
  {
    title: "Agent 3: trend-to-content",
    lines: [
      "Reading SKILL.md...",
      "Creating root README.md",
      "  wrote README.md (1.2kb)",
      "Fixing packaging structure",
      "  moved assets/ to bundle",
      "Creating LICENSE (MIT)",
      "All 3 issues resolved.",
    ],
  },
  {
    title: "Agent 4: prompt-reviewer",
    lines: [
      "Reading SKILL.md...",
      "Removing nested duplicate/",
      "Removing unused dependencies",
      "  cleaned pyproject.toml",
      "Creating LICENSE (MIT)",
      "Fixing packaging issue",
      "All 4 issues resolved.",
    ],
  },
];

/**
 * ACT 2: DIVIDE-AND-CONQUER (34s = 1020 frames)
 * Audio: 32.55s
 *
 * Narrator beats:
 *   0–4s:   "So I invoke divide-and-conquer."
 *   4–10s:  "It reads the issues and splits them into 4 independent agents —
 *            one per directory."
 *   10–16s: "Each agent owns its own files. The conflict check confirms zero
 *            write overlap."
 *   16–20s: "All 4 agents launch in a single message."
 *   20–28s: speed ramp — "Nested duplicates deleted. Bare except fixed..."
 *   28–32s: "Done. Every issue resolved, no conflicts."
 *
 * Timeline:
 *   0–25:     type command (~0.8s)
 *   30–270:   plan streams (12 lines over ~8s = 1.5 l/s)
 *   270–360:  conflict check highlight (1–3s)
 *   390–450:  plan fades → 2×2 grid enters
 *   450–840:  agents run at 2× speed (~13s of screen time)
 *   840–900:  all complete
 *   900–1020: completed banner holds
 */
export const Act2Scene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Command
  const CMD_CPF = 0.5;
  const cmdChars = Math.min(
    COMMAND.length,
    Math.floor(Math.max(0, frame - 5) * CMD_CPF),
  );
  const cmdDone = cmdChars >= COMMAND.length;

  // Plan stream — 1.5 lines/sec starting at 1s
  const PLAN_START = fps;
  const PLAN_LPS = 1.5;
  const planCount = Math.floor(
    Math.max(0, frame - PLAN_START) * (PLAN_LPS / fps),
  );
  const visiblePlan = PLAN_LINES.slice(
    0,
    Math.min(PLAN_LINES.length, planCount),
  );
  const planDone = planCount >= PLAN_LINES.length;

  // Conflict check highlight — appears once plan finishes
  const conflictIdx = PLAN_LINES.findIndex((l) => l.includes("Conflict"));
  const planDoneFrame = PLAN_START + Math.ceil(PLAN_LINES.length / PLAN_LPS) * fps;
  const conflictGlow =
    planDone
      ? interpolate(
          frame,
          [planDoneFrame, planDoneFrame + fps * 0.5],
          [0, 1],
          { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
        )
      : 0;

  // Grid transition — at ~13s
  const GRID_START = Math.round(fps * 13);
  const showGrid = frame >= GRID_START;
  const gridIn = spring({
    frame: frame - GRID_START,
    fps,
    config: { damping: 18, stiffness: 90 },
  });

  // Agents complete at ~28s
  const COMPLETED_FRAME = Math.round(fps * 28);
  const SPEED = 2;

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg, padding: 60 }}>
      {/* Terminal + plan — fades when grid appears */}
      <div
        style={{
          position: "absolute",
          inset: 60,
          opacity: showGrid ? 1 - gridIn : 1,
          transform: showGrid
            ? `scale(${interpolate(gridIn, [0, 1], [1, 0.92])})`
            : undefined,
          pointerEvents: showGrid ? "none" : undefined,
        }}
      >
        <Terminal title="~/repos/skills — divide-and-conquer">
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
              {visiblePlan.map((line, i) => {
                const inConflictBlock =
                  i >= conflictIdx && i <= conflictIdx + 3;
                return (
                  <div
                    key={i}
                    style={{
                      color:
                        inConflictBlock && conflictGlow > 0.5
                          ? line.includes("0") || line.includes("SAFE")
                            ? COLORS.green
                            : COLORS.text
                          : line.startsWith("  Agent")
                            ? COLORS.blue
                            : COLORS.text,
                      backgroundColor:
                        inConflictBlock && conflictGlow > 0.5
                          ? COLORS.green + "12"
                          : "transparent",
                    }}
                  >
                    {line || "\u00A0"}
                  </div>
                );
              })}
            </div>
          )}
        </Terminal>
      </div>

      {/* 2×2 agent grid */}
      {showGrid && (
        <div
          style={{
            position: "absolute",
            inset: 60,
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gridTemplateRows: "1fr 1fr",
            gap: 16,
            opacity: gridIn,
          }}
        >
          {AGENTS.map((agent, i) => (
            <AgentPanel
              key={agent.title}
              title={agent.title}
              lines={agent.lines}
              startFrame={GRID_START + i * 3}
              speedMultiplier={SPEED}
              completedFrame={COMPLETED_FRAME}
            />
          ))}
        </div>
      )}

      {/* 2× speed badge */}
      {showGrid && frame < COMPLETED_FRAME && (
        <Sequence from={0} layout="none">
          <div
            style={{
              position: "absolute",
              top: 30,
              right: 30,
              backgroundColor: COLORS.yellow + "33",
              border: `1px solid ${COLORS.yellow}`,
              borderRadius: 20,
              padding: "4px 14px",
              fontFamily: '"JetBrains Mono", monospace',
              fontSize: 13,
              color: COLORS.yellow,
              opacity: gridIn,
            }}
          >
            2× speed
          </div>
        </Sequence>
      )}

      {/* Completed banner */}
      {frame >= COMPLETED_FRAME && (
        <div
          style={{
            position: "absolute",
            bottom: 30,
            left: "50%",
            transform: `translateX(-50%) scale(${interpolate(
              spring({
                frame: frame - COMPLETED_FRAME,
                fps,
                config: { damping: 15, stiffness: 100 },
              }),
              [0, 1],
              [0.9, 1],
            )})`,
            backgroundColor: COLORS.green + "22",
            border: `1px solid ${COLORS.green}`,
            borderRadius: 8,
            padding: "10px 28px",
            fontFamily: '"JetBrains Mono", monospace',
            fontSize: 18,
            color: COLORS.green,
            fontWeight: 700,
          }}
        >
          All 12 issues resolved — 0 conflicts
        </div>
      )}
    </AbsoluteFill>
  );
};
