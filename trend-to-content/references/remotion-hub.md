# Centralized Videos Hub

Store videos in their respective repos (to use local imports, components, shared code), but aggregate them into a central hub for unified preview and rendering.

## Architecture

```
~/repos/videos/                      # Central hub (npm run studio here)
├── src/
│   ├── index.ts                     # registerRoot
│   └── Root.tsx                     # Imports all project compositions
├── linked/                          # Symlinks to each project
│   ├── project-a/ →                 /path/to/project-a/videos
│   └── project-b/ →                 /path/to/project-b/promo
├── package.json
├── tsconfig.json
└── remotion.config.ts

~/repos/project-a/videos/            # Project-specific videos
├── src/
│   └── Compositions.tsx             # Exports <ProjectACompositions />
├── concept-1/
│   ├── Concept1.tsx
│   └── components/
└── shared/                          # Project-specific shared components
```

## Setup

### 1. Hub package.json

```json
{
  "name": "videos-hub",
  "scripts": {
    "studio": "remotion studio src/index.ts",
    "render": "remotion render src/index.ts"
  },
  "dependencies": {
    "remotion": "^4.0.410",
    "@remotion/cli": "^4.0.410",
    "@remotion/google-fonts": "^4.0.410",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "typescript": "^5.0.0"
  }
}
```

### 2. Hub src/index.ts

```tsx
import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root";

registerRoot(RemotionRoot);
```

### 3. Hub src/Root.tsx

```tsx
import { ProjectACompositions } from "../linked/project-a/src/Compositions";
import { ProjectBCompositions } from "../linked/project-b/Compositions";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <ProjectACompositions />
      <ProjectBCompositions />
    </>
  );
};
```

### 4. Project Compositions.tsx (each project)

```tsx
import { Composition, Folder } from "remotion";
import { MyConcept } from "./concept-1/MyConcept";

// Export compositions - NO registerRoot here
export const ProjectACompositions: React.FC = () => {
  return (
    <Folder name="ProjectA">
      <Composition
        id="MyConcept"
        component={MyConcept}
        durationInFrames={1800}
        fps={30}
        width={1080}
        height={1920}
        defaultProps={{}}
      />
    </Folder>
  );
};
```

### 5. Create symlinks

```bash
cd ~/repos/videos
ln -s /path/to/project-a/videos ./linked/project-a
ln -s /path/to/project-b/promo ./linked/project-b
```

## Key Rules

1. **Only the hub calls `registerRoot()`** - Projects export composition components only
2. **Folder names: a-z, A-Z, 0-9, and `-` only** - No spaces
3. **Avoid circular dependencies** - Extract shared constants (like COLORS) to separate files
4. **Hub owns node_modules** - All projects use the hub's Remotion version

## Adding a New Project

```bash
# 1. Create symlink
ln -s /path/to/new-project/videos ./linked/new-project

# 2. Create Compositions.tsx in the project (see template above)

# 3. Import in hub's Root.tsx
import { NewProjectCompositions } from "../linked/new-project/src/Compositions";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <ExistingCompositions />
      <NewProjectCompositions />  {/* Add here */}
    </>
  );
};
```

## Public Assets (staticFile)

When projects use `staticFile()` for images/assets, those files live in each project's `public/` folder. The hub needs copies of all of them.

**Important:** Symlinks don't work - the Remotion server doesn't follow them. Copy the actual files.

```bash
# Copy all files from a project's public folder to the hub
cp /path/to/project/video/public/* ~/repos/videos/public/
```

**Note:** This flattens all assets into one folder. If two projects have files with the same name, they'll conflict. Namespace your files (e.g., `project-a-hero.jpg`, `project-b-logo.png`) to avoid collisions.

Hub public assets location: `~/repos/videos/public/`

## Circular Dependency Fix

If you see `Cannot access 'X' before initialization`, extract constants to a separate file:

```tsx
// BAD: Composition.tsx exports COLORS, components import from Composition
// Creates circular: Composition → Scene → Component → Composition

// GOOD: colors.ts exports COLORS, everyone imports from colors.ts
// colors.ts
export const COLORS = { bg: "#1e1e1e", text: "#d4d4d4" };

// Composition.tsx
import { COLORS } from "./colors";
export { COLORS } from "./colors"; // Re-export for backwards compat

// Component.tsx
import { COLORS } from "../colors"; // Import from colors.ts directly
```
