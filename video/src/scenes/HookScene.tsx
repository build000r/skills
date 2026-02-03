import React from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";
import { COLORS } from "../colors";

const LINE_1 =
  "This video was planned and scripted by the skills in this repo.";
const LINE_2 = "Here's the proof.";

/**
 * HOOK (6s = 180 frames)
 * Audio: 4.69s — narrator reads both lines with a brief beat between.
 *
 * Timeline:
 *   0–10:    fade in from black
 *   5–95:    line 1 types (~3s, matching narration pace)
 *   95–115:  beat — cursor blinks on finished line 1
 *   115–140: line 2 types (~0.8s, punchy)
 *   140–180: hold — cursor blinks
 */
export const HookScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const fadeIn = interpolate(frame, [0, 10], [0, 1], {
    extrapolateRight: "clamp",
  });

  // Line 1: 62 chars over ~90 frames (0.69 c/f ≈ narrator pace)
  const L1_START = 5;
  const L1_CPF = 0.69;
  const l1Elapsed = Math.max(0, frame - L1_START);
  const l1Chars = Math.min(LINE_1.length, Math.floor(l1Elapsed * L1_CPF));
  const l1Done = l1Chars >= LINE_1.length;
  const l1End = L1_START + Math.ceil(LINE_1.length / L1_CPF); // ~95

  // Beat
  const BEAT = fps; // 30 frames = 1s
  const L2_START = l1End + BEAT; // ~125

  // Line 2: 18 chars, fast and punchy
  const L2_CPF = 0.9;
  const l2Elapsed = Math.max(0, frame - L2_START);
  const l2Chars = Math.min(LINE_2.length, Math.floor(l2Elapsed * L2_CPF));
  const l2Done = l2Chars >= LINE_2.length;

  // Cursor
  const cursorBlink = interpolate(frame % 24, [0, 12, 24], [1, 0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  const showL2 = frame >= L2_START;

  return (
    <AbsoluteFill
      style={{
        backgroundColor: COLORS.bg,
        opacity: fadeIn,
        justifyContent: "center",
        alignItems: "center",
      }}
    >
      <div
        style={{
          width: 1400,
          display: "flex",
          flexDirection: "column",
          gap: 24,
          fontFamily: '"JetBrains Mono", "Fira Code", monospace',
          fontSize: 42,
          fontWeight: 500,
          lineHeight: 1.5,
          color: COLORS.text,
        }}
      >
        <div>
          <span>{LINE_1.slice(0, l1Chars)}</span>
          {l1Chars > 0 && !showL2 && (
            <span
              style={{
                color: COLORS.cursor,
                opacity: l1Done ? cursorBlink : 1,
              }}
            >
              ▎
            </span>
          )}
        </div>

        {showL2 && (
          <div>
            <span style={{ color: COLORS.white }}>
              {LINE_2.slice(0, l2Chars)}
            </span>
            {l2Chars > 0 && (
              <span
                style={{
                  color: COLORS.cursor,
                  opacity: l2Done ? cursorBlink : 1,
                }}
              >
                ▎
              </span>
            )}
          </div>
        )}
      </div>
    </AbsoluteFill>
  );
};
