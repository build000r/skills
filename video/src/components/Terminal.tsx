import React from "react";
import { COLORS } from "../colors";

interface TerminalProps {
  children: React.ReactNode;
  title?: string;
  padding?: string;
}

export const Terminal: React.FC<TerminalProps> = ({
  children,
  title = "zsh",
  padding = "24px 32px",
}) => {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        backgroundColor: COLORS.terminalBg,
        borderRadius: 12,
        overflow: "hidden",
        border: `1px solid ${COLORS.terminalHeader}`,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          height: 40,
          backgroundColor: COLORS.terminalHeader,
          padding: "0 16px",
          gap: 8,
          flexShrink: 0,
        }}
      >
        <div
          style={{
            width: 12,
            height: 12,
            borderRadius: "50%",
            backgroundColor: COLORS.red,
          }}
        />
        <div
          style={{
            width: 12,
            height: 12,
            borderRadius: "50%",
            backgroundColor: COLORS.yellow,
          }}
        />
        <div
          style={{
            width: 12,
            height: 12,
            borderRadius: "50%",
            backgroundColor: COLORS.green,
          }}
        />
        <div
          style={{
            flex: 1,
            textAlign: "center",
            color: COLORS.dimText,
            fontSize: 13,
            fontFamily: "monospace",
          }}
        >
          {title}
        </div>
      </div>
      <div
        style={{
          flex: 1,
          padding,
          fontFamily: '"JetBrains Mono", "Fira Code", "SF Mono", monospace',
          fontSize: 20,
          lineHeight: 1.6,
          color: COLORS.text,
          overflow: "hidden",
        }}
      >
        {children}
      </div>
    </div>
  );
};

export const PromptLine: React.FC<{ children?: React.ReactNode }> = ({
  children,
}) => {
  return (
    <div style={{ display: "flex", gap: 8 }}>
      <span style={{ color: COLORS.prompt }}>❯</span>
      {children}
    </div>
  );
};

export const OutputLine: React.FC<{
  children: React.ReactNode;
  color?: string;
  indent?: number;
}> = ({ children, color = COLORS.text, indent = 0 }) => {
  return (
    <div style={{ color, paddingLeft: indent * 16 }}>{children}</div>
  );
};
