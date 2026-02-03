import React from "react";
import { Composition, Folder } from "remotion";
import { SkillsDemo } from "./SkillsDemo";
import { FPS, TOTAL_DURATION } from "./colors";

export const SkillsCompositions: React.FC = () => {
  return (
    <Folder name="Skills">
      <Composition
        id="SkillsDemo"
        component={SkillsDemo}
        durationInFrames={TOTAL_DURATION * FPS}
        fps={FPS}
        width={1920}
        height={1080}
        defaultProps={{}}
      />
    </Folder>
  );
};
