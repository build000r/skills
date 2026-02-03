import React from "react";
import {
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  spring,
} from "remotion";
import { COLORS } from "../colors";

interface AgentPanelProps {
  title: string;
  lines: string[];
  startFrame: number;
  speedMultiplier?: number;
  completedFrame?: number;
}

export const AgentPanel: React.FC<AgentPanelProps> = ({
  title,
  lines,
  startFrame,
  speedMultiplier = 1,
  completedFrame = Infinity,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const elapsed = Math.max(0, (frame - startFrame) * speedMultiplier);

  const visibleLines = lines.filter((_, i) => {
    const lineAppearFrame = i * (fps * 0.3);
    return elapsed >= lineAppearFrame;
  });

  const isCompleted = frame >= completedFrame;

  const entranceProgress = spring({
    frame: frame - startFrame,
    fps,
    config: { damping: 20, stiffness: 120 },
  });

  const scale = interpolate(entranceProgress, [0, 1], [0.95, 1]);
  const opacity = interpolate(entranceProgress, [0, 0.5], [0, 1], {
    extrapolateRight: "clamp",
  });

  return (
    <div
      style={{
        flex: 1,
        backgroundColor: COLORS.surface,
        borderRadius: 8,
        border: `1px solid ${isCompleted ? COLORS.green : COLORS.terminalHeader}`,
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        opacity,
        transform: `scale(${scale})`,
      }}
    >
      <div
        style={{
          padding: "8px 12px",
          backgroundColor: COLORS.terminalHeader,
          borderBottom: `1px solid ${COLORS.terminalHeader}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontFamily: '"JetBrains Mono", monospace',
            fontSize: 13,
            color: COLORS.blue,
          }}
        >
          {title}
        </span>
        {isCompleted && (
          <span
            style={{
              fontFamily: '"JetBrains Mono", monospace',
              fontSize: 12,
              color: COLORS.green,
            }}
          >
            completed
          </span>
        )}
      </div>
      <div
        style={{
          flex: 1,
          padding: "8px 12px",
          fontFamily: '"JetBrains Mono", monospace',
          fontSize: 11,
          lineHeight: 1.5,
          color: COLORS.dimText,
          overflow: "hidden",
        }}
      >
        {visibleLines.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
        {!isCompleted && visibleLines.length > 0 && (
          <span
            style={{
              color: COLORS.cursor,
              opacity: interpolate(frame % 20, [0, 10, 20], [1, 0.3, 1]),
            }}
          >
            _
          </span>
        )}
      </div>
    </div>
  );
};
