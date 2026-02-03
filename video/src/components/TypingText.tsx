import React from "react";
import { useCurrentFrame, interpolate } from "remotion";
import { COLORS } from "../colors";

interface TypingTextProps {
  text: string;
  startFrame?: number;
  charsPerFrame?: number;
  showCursor?: boolean;
  color?: string;
  fontSize?: number;
  fontWeight?: number;
}

export const TypingText: React.FC<TypingTextProps> = ({
  text,
  startFrame = 0,
  charsPerFrame = 0.5,
  showCursor = true,
  color = COLORS.text,
  fontSize = 20,
  fontWeight = 400,
}) => {
  const frame = useCurrentFrame();
  const elapsed = Math.max(0, frame - startFrame);
  const charCount = Math.min(text.length, Math.floor(elapsed * charsPerFrame));
  const displayText = text.slice(0, charCount);
  const isDone = charCount >= text.length;

  const cursorOpacity = interpolate(frame % 30, [0, 15, 30], [1, 0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  if (elapsed < 0) return null;

  return (
    <span
      style={{
        color,
        fontSize,
        fontWeight,
        fontFamily: '"JetBrains Mono", "Fira Code", monospace',
      }}
    >
      {displayText}
      {showCursor && charCount > 0 && (
        <span
          style={{
            opacity: isDone ? cursorOpacity : 1,
            color: COLORS.cursor,
          }}
        >
          ▎
        </span>
      )}
    </span>
  );
};

/**
 * Returns the number of frames needed to type the full text.
 */
export const typingDuration = (
  text: string,
  charsPerFrame: number = 0.5,
): number => {
  return Math.ceil(text.length / charsPerFrame);
};
