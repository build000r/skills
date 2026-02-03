import React from "react";
import { useCurrentFrame, spring, useVideoConfig, interpolate } from "remotion";
import { COLORS } from "../colors";

interface CaptionBadgeProps {
  label: string;
  delay: number;
  color?: string;
}

export const CaptionBadge: React.FC<CaptionBadgeProps> = ({
  label,
  delay,
  color = COLORS.red,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const progress = spring({
    frame: frame - delay,
    fps,
    config: { damping: 15, stiffness: 120 },
  });

  const scale = interpolate(progress, [0, 1], [0.8, 1]);
  const opacity = interpolate(progress, [0, 0.3], [0, 1], {
    extrapolateRight: "clamp",
  });

  if (frame < delay) return null;

  return (
    <div
      style={{
        opacity,
        transform: `scale(${scale})`,
        backgroundColor: color + "22",
        border: `1px solid ${color}`,
        borderRadius: 6,
        padding: "6px 14px",
        fontFamily: '"JetBrains Mono", monospace',
        fontSize: 16,
        color,
        whiteSpace: "nowrap",
        display: "inline-block",
      }}
    >
      {label}
    </div>
  );
};

interface CaptionBadgeStackProps {
  labels: { text: string; color?: string }[];
  startFrame: number;
  stagger?: number;
}

export const CaptionBadgeStack: React.FC<CaptionBadgeStackProps> = ({
  labels,
  startFrame,
  stagger = 30,
}) => {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
        position: "absolute",
        right: 60,
        top: 120,
      }}
    >
      {labels.map((item, i) => (
        <CaptionBadge
          key={item.text}
          label={item.text}
          delay={startFrame + i * stagger}
          color={item.color}
        />
      ))}
    </div>
  );
};
