import React from "react";
import { AbsoluteFill, Audio, Sequence, staticFile, useVideoConfig } from "remotion";
import { COLORS, TIMINGS, TITLE_CARD_DURATION } from "./colors";
import { HookScene } from "./scenes/HookScene";
import { ContextScene } from "./scenes/ContextScene";
import { Act1Scene } from "./scenes/Act1Scene";
import { Act2Scene } from "./scenes/Act2Scene";
import { Act3Scene } from "./scenes/Act3Scene";
import { CtaScene } from "./scenes/CtaScene";

const SCENES = [
  {
    key: "hook",
    timing: TIMINGS.hook,
    Scene: HookScene,
    audio: "skills-demo-01-hook.mp3",
  },
  {
    key: "context",
    timing: TIMINGS.context,
    Scene: ContextScene,
    audio: "skills-demo-02-context.mp3",
  },
  {
    key: "act1",
    timing: TIMINGS.act1,
    Scene: Act1Scene,
    audio: "skills-demo-03-act1.mp3",
  },
  {
    key: "act2",
    timing: TIMINGS.act2,
    Scene: Act2Scene,
    audio: "skills-demo-04-act2.mp3",
  },
  {
    key: "act3",
    timing: TIMINGS.act3,
    Scene: Act3Scene,
    audio: "skills-demo-05-act3.mp3",
  },
  {
    key: "cta",
    timing: TIMINGS.cta,
    Scene: CtaScene,
    audio: "skills-demo-06-cta.mp3",
  },
] as const;

/**
 * Main composition: 2:45 at 30fps = 4950 frames, 1920x1080.
 *
 * Each scene is placed via <Sequence> at its absolute start frame.
 * Audio tracks are layered in parallel Sequences so they play
 * at the correct global time regardless of scene transitions.
 */
export const SkillsDemo: React.FC = () => {
  const { fps } = useVideoConfig();

  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg }}>
      {/* Static title card — visible as the poster/thumbnail frame */}
      <Sequence durationInFrames={TITLE_CARD_DURATION * fps}>
        <AbsoluteFill
          style={{
            backgroundColor: COLORS.bg,
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
              This video was planned and scripted by the skills in this repo.
            </div>
            <div style={{ color: COLORS.white }}>
              Here's the proof.
              <span style={{ color: COLORS.cursor }}>▎</span>
            </div>
          </div>
        </AbsoluteFill>
      </Sequence>

      {SCENES.map(({ key, timing, Scene, audio }) => {
        const startFrame = timing.start * fps;
        const durationFrames = timing.duration * fps;

        return (
          <React.Fragment key={key}>
            {/* Visual scene */}
            <Sequence
              from={startFrame}
              durationInFrames={durationFrames}
              premountFor={fps}
            >
              <Scene />
            </Sequence>

            {/* Audio track */}
            <Sequence from={startFrame} layout="none">
              <Audio src={staticFile(audio)} />
            </Sequence>
          </React.Fragment>
        );
      })}
    </AbsoluteFill>
  );
};
