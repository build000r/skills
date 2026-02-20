# Example Frontend Patterns Reference

> **This is a complete example** of what a mode's `patterns_reference` should look like.
> Copy this file, rename your primitives, adjust your paths, and drop it in your mode.
>
> The scaffolder reads your patterns reference before generating ANY code.
> The reviewer audits generated code AGAINST your patterns reference.
> If this file is thin, your scaffolded code will be generic. If it's opinionated, your code will be consistent.

---

## Architecture at a Glance

```
src/
├── features/           # Feature domains: billing, messaging, scheduling, etc.
│   └── {feature}/
│       ├── api/        # Feature-scoped API functions
│       ├── components/ # Feature-scoped components
│       ├── hooks/      # Feature-scoped hooks
│       ├── state/      # Zustand stores (complex client state)
│       ├── pages/      # Route pages
│       └── types/      # Feature types
├── components/         # Shared UI: primitives/, widgets/, ui/, charts/, layout/
├── hooks/              # Shared hooks: useLocalStorageState, useFormState, etc.
├── contexts/           # React Context: AuthContext, ThemeContext, LayoutContext
├── lib/api/            # Shared API client + domain APIs
├── services/           # Business logic layer (wraps API calls with transforms)
├── routes/             # Router config + ProtectedRoute
├── types/              # Cross-feature TypeScript types
└── config/             # App configuration
```

### 3-Tier Data Architecture

```
Tier 1: API calls       lib/api/client.ts + features/{feature}/api/
                         Raw HTTP. Request/response mapping. snake_case → camelCase.

Tier 2: Services         services/
                         Business logic. Composes API calls. Transforms data.
                         Does NOT manage state.

Tier 3: State            Zustand stores (features/{feature}/state/)
                         or React Query (inline in hooks/components)
                         Manages loading, caching, reactivity.
```

**When to use which tier:**
- **Simple server data** (list, detail, create, update): Skip services, use React Query directly with API functions
- **Complex business logic** (multi-step operations, data transforms, caching rules): Add a service layer
- **Complex client state** (multi-field state, optimistic updates, cross-component mutations): Add a Zustand store

### Data Flow

```
API client (lib/api/client.ts) → Service (services/) → Store or Query → Component
         httpClient()              business logic      Zustand / Query    UI
```

### State Strategy Decision Tree

| Need | Use | NOT |
|------|-----|----|
| Server data (fetch/cache/refetch) | **Query hooks** (`useQuery`) | Manual useState + useEffect |
| Complex client state with mutations | **Zustand** store | Prop drilling through 5 components |
| UI preferences (persisted) | **useLocalStorageState** | Manual localStorage.get/setItem |
| Global app state (auth, theme) | **React Context** | Zustand (overkill for read-mostly state) |
| Form state | **react-hook-form** or simple useState | useReducer (usually unnecessary) |

### Where Does This File Go?

| Creating | Put it in |
|----------|-----------|
| New API function | `src/features/{feature}/api/` (or `src/lib/api/{domain}/` if cross-feature) |
| New service (business logic) | `src/services/` |
| New Zustand store | `src/features/{feature}/state/` |
| Feature-scoped hook | `src/features/{feature}/hooks/` |
| Shared hook (2+ features) | `src/hooks/` |
| Feature-scoped component | `src/features/{feature}/components/` |
| Shared component | `src/components/` (find the right subdirectory) |
| New page/route | `src/features/{feature}/pages/` + register in router config |
| Feature types | `src/features/{feature}/types/` (or colocate in `api/types.ts`) |
| Cross-feature types | `src/types/` |

---

## CRITICAL RULES

### 1. FULL-STACK BY DEFAULT

**All features that involve data are full-stack.** Data lives in the backend database, accessed via API endpoints.

```
WRONG: "I'll store this in localStorage for now"
WRONG: "Let me create a mock/stub until the backend is ready"
RIGHT: "This needs a backend endpoint — let me check the backend repo or ask the user"
```

**If unclear, USE AskUserQuestion:**
> "Does this feature need a backend endpoint, or is this purely client-side UI state?"

### 2. EDIT EXISTING COMPONENTS — DON'T CREATE NEW ONES

**Always search for existing components before creating new ones.**

Before creating ANY new component:
1. Search for similar components: `Glob` for `**/Component*.tsx`, `**/*Widget*.tsx`
2. Check if an existing component can be extended with new props
3. Check if the feature belongs in an existing widget/page

```
WRONG: Creating AdvancedTaskList.tsx when TaskList.tsx already exists
RIGHT: Adding `variant="advanced"` prop to existing TaskList.tsx

WRONG: Creating NewItemCard.tsx
RIGHT: Extending existing ItemCard.tsx with new variant prop
```

**If unclear, USE AskUserQuestion:**
> "I found existing {ComponentName}. Should I extend it, or create a separate component?"

### When Extraction IS Appropriate

While the default is to extend existing code, extraction makes sense when:

**Extract a hook when:**
- Same data-fetching/mutation logic used in 2+ components
- Complex state logic (>30 lines) that obscures component rendering
- Logic needs unit testing independent of UI

**Extract a component when:**
- Same UI pattern appears in 3+ places with identical structure
- A section of JSX exceeds ~100 lines and has clear boundaries
- The component needs its own loading/error states

**Extract a utility when:**
- Same transformation/calculation used in 3+ files
- Logic is pure (no React, no side effects)

**DON'T extract when:**
- "It might be reused someday" (YAGNI)
- Two uses with slightly different needs (leads to prop sprawl)
- It's just moving code to a different file without simplification

### 3. COMPONENT SIZE LIMITS

| Threshold | Action |
|-----------|--------|
| <300 LOC | Preferred — leave it alone |
| 300-400 LOC | Acceptable if logic is cohesive — flag for future extraction |
| >400 LOC | **MUST extract** — split into sub-components or hooks |

### 4. localStorage IS FOR UI STATE ONLY

The storage hook is ONLY for persisting **UI preferences**, NOT data:

**CORRECT uses of localStorage:**
- Filter/tab selections: `useLocalStorageState('insights-filter', 'all')`
- Expanded/collapsed state: `useLocalStorageState('panel-expanded', true)`
- User preferences: `useLocalStorageState('theme', 'light')`

**WRONG uses of localStorage:**
- Storing entities/records (use backend DB + query hooks)
- Caching API responses (query hooks handle this)
- "Temporary" data storage (this always becomes permanent technical debt)

**If a feature involves storing/retrieving data, it needs a backend endpoint.**

---

## Component Library Primitives

> **Replace these names** with your project's actual primitives.
> The point is: you HAVE primitives, and the scaffolder MUST use them.

### Panel (Container/Card)

The universal container for content blocks. Never use inline `rounded-xl border bg-white` patterns.

```tsx
<Panel tone="default" padding="md">
  {content}
</Panel>
```

**Props:**
- `tone`: `'default'` | `'muted'` | `'contrast'` | `'plain'`
  - `default` — Standard card with border and background
  - `muted` — De-emphasized background for nested content
  - `contrast` — Dark/inverted background for focused content
  - `plain` — Transparent, no styling
- `padding`: `'none'` | `'xs'` | `'sm'` | `'md'` | `'lg'`
- `interactive`: boolean — Adds hover/lift effect
- `className`: string — Additional CSS classes

### Toolbar (Header Row)

Horizontal layout for widget/section headers.

```tsx
<Toolbar
  start={<SectionHeading>Title</SectionHeading>}
  end={<Button size="sm">Action</Button>}
  bordered
/>
```

**Props:**
- `start`: ReactNode — Left content
- `center`: ReactNode — Center content (optional)
- `end`: ReactNode — Right content
- `bordered`: boolean — Bottom border

### Button

All clickable actions. Never use inline `<button className="bg-...">` patterns.

```tsx
<Button tone="primary" size="md" onClick={handleClick}>
  Save
</Button>
```

**Props:**
- `tone`: `'primary'` | `'secondary'` | `'outline'` | `'subtle'` | `'danger'`
  - `primary` — Main CTA, filled accent color
  - `secondary` — Bordered accent color
  - `outline` — Transparent with border
  - `subtle` — No background, shows on hover
  - `danger` — Red/destructive styling
- `size`: `'sm'` | `'md'` | `'lg'`
- `block`: boolean — Full width
- `disabled`: boolean

### LoadingState

Shown during initial data load. Never build custom spinners.

```tsx
<LoadingState message="Loading tasks..." />
```

**Props:**
- `message`: ReactNode (default: "Loading...")
- `tone`: Panel tone (default: "muted")
- `skeleton`: ReactNode — Custom skeleton layout instead of spinner

### ErrorState

Shown when data fetching fails. MUST include retry capability.

```tsx
<ErrorState
  title="Something went wrong"
  message="Failed to load data"
  onRetry={refetch}
/>
```

**Props:**
- `title`: ReactNode (default: "Something went wrong")
- `message`: ReactNode (required)
- `onRetry`: () => void — Shows "Retry" button

### EmptyState

Shown when query returns zero results. Never leave a blank screen.

```tsx
<EmptyState
  message="No tasks yet"
  icon={<PlusCircle />}
  action={<Button>Create Task</Button>}
/>
```

**Props:**
- `message`: ReactNode (required)
- `icon`: ReactNode
- `action`: ReactNode — CTA button

### StatusBadge

Inline status indicators.

```tsx
<StatusBadge tone="success" icon={<CheckIcon />}>Complete</StatusBadge>
```

**Props:**
- `tone`: `'neutral'` | `'info'` | `'success'` | `'warning'` | `'danger'`
- `icon`: ReactNode

### ChipGroup (Filters)

Filter chip bar for list views.

```tsx
<ChipGroup
  options={[
    { id: 'all', label: 'All' },
    { id: 'active', label: 'Active' },
    { id: 'complete', label: 'Complete' },
  ]}
  value={selectedFilter}
  onChange={setSelectedFilter}
/>
```

**Props:**
- `options`: `{ id: string; label: ReactNode }[]`
- `value`: string | string[]
- `onChange`: (value) => void
- `multiple`: boolean — Allow multi-select

### SectionHeading

Consistent heading typography within panels.

```tsx
<SectionHeading helper="Configure settings">
  Section Title
</SectionHeading>
```

### Callout (Feedback)

Contextual notices and warnings.

```tsx
<Callout variant="warning" title="Important">
  Your session will expire in 5 minutes.
</Callout>
```

**Props:**
- `variant`: `'info'` | `'success'` | `'warning'` | `'error'`
- `title`: string

### WidgetShell (Dashboard Wrapper)

The core wrapper for all dashboard widgets. Manages layout position, width, expand/collapse, and provides state to children via render props.

```tsx
<WidgetShell
  id="my-widget"              // Required: unique ID for layout state persistence
  title="My Widget"           // Required: display title
  defaultWidthStep={1}        // 1 | 2 | 3 (narrow/medium/full)
  defaultExpanded={false}     // Initial expand state
  hideHeader                  // Hide default header (for custom headers)
  hideExpandToggle            // Hide expand/collapse buttons
>
  {({ expanded, widthStep, maxWidthStep, setExpanded, setWidthStep }) => (
    <div>{expanded ? 'Full content' : 'Summary'}</div>
  )}
</WidgetShell>
```

**Render-prop children receive:**
- `expanded`: boolean — Current expanded state
- `widthStep`: number — Current width (1-3)
- `maxWidthStep`: number — Maximum width
- `setExpanded`: (expanded: boolean) => void
- `setWidthStep`: (step: number) => void
- `collapse`: () => void

### Fullscreen Overlay

Full-screen expansion mode for widgets that need more space (editors, chat, detail views).

```tsx
<FullscreenSurface
  open={isFullscreen}
  onClose={() => setIsFullscreen(false)}
  tone="white"
  animation="slide-up"
>
  <FullscreenHeader
    title="Widget Title"
    onClose={() => setIsFullscreen(false)}
  />
  <div className="flex-1 min-h-0 overflow-auto p-4">
    {/* Full content */}
  </div>
</FullscreenSurface>
```

**FullscreenSurface Props:**
- `open`: boolean — Whether visible
- `onClose`: () => void — Called on escape key or close
- `tone`: `'white'` | `'tan'` | `'sand'`
- `animation`: `'slide-up'` | `'fade'` | `'none'`

**FullscreenToggle** — Button to enter fullscreen mode, placed in widget headers:
```tsx
<FullscreenToggle onEnter={() => setIsFullscreen(true)} />
```

### LockedState (Gated/Paywalled Content)

Shown when content requires an upgrade, purchase, or unlock action. Text MUST never be truncated.

```tsx
<LockedState
  title="Premium Content"
  message="Unlock to access guided walkthroughs and downloads."
  action={<Button tone="primary">Unlock</Button>}
  secondaryAction={<Button tone="subtle">Maybe Later</Button>}
/>
```

**Props:**
- `title`: ReactNode (required) — **NEVER truncated**
- `message`: ReactNode — **NEVER truncated**
- `icon`: ReactNode (default: Lock icon)
- `action`: ReactNode — Primary CTA button
- `secondaryAction`: ReactNode — Escape hatch / dismiss
- `variant`: `'default'` | `'compact'` | `'card'`
  - `default` — Centered layout with icon circle
  - `compact` — Horizontal inline layout
  - `card` — Preview image with overlay content

```tsx
// WRONG — inline locked content styling
<div className="flex items-center gap-2">
  <Lock size={16} />
  <span>Purchase to unlock</span>
  <button>Buy Now</button>
</div>

// RIGHT — use LockedState primitive
<LockedState
  title="Premium Content"
  message="Purchase to unlock"
  action={<Button>Buy Now</Button>}
/>
```

---

## Data Fetching Patterns

### Read Data — useQuery

```tsx
import { useQuery } from '@tanstack/react-query';

const { data = [], isPending, error, refetch } = useQuery({
  queryKey: ['tasks', projectId],       // Cache key — include ALL dependencies
  queryFn: () => fetchTasks(projectId), // Async function that returns data
  enabled: !!projectId,                 // Only fetch when condition is true
  staleTime: 5 * 60 * 1000,            // Data fresh for 5 minutes
});
```

### Write Data — useMutation

```tsx
import { useMutation, useQueryClient } from '@tanstack/react-query';

const queryClient = useQueryClient();

const { mutate, mutateAsync, isPending } = useMutation({
  mutationFn: (data) => createTask(data),
  onSuccess: () => {
    // Invalidate related queries to refetch
    queryClient.invalidateQueries({ queryKey: ['tasks'] });
  },
});
```

### Centralized Query Key Factory

Every feature MUST centralize its query keys:

```tsx
// features/{slice}/hooks/queryKeys.ts
export const taskKeys = {
  all:      ['tasks'] as const,
  lists:    () => [...taskKeys.all, 'list'] as const,
  list:     (filters: TaskFilters) => [...taskKeys.lists(), filters] as const,
  details:  () => [...taskKeys.all, 'detail'] as const,
  detail:   (id: string) => [...taskKeys.details(), id] as const,
};
```

This prevents cache key drift and ensures proper invalidation.

### Complete Data Hook Pattern

```tsx
// features/{slice}/hooks/use{Slice}.ts
import { useCallback, useMemo } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { taskKeys } from "./queryKeys";
import { listTasks, createTask, type Task } from "../api/taskApi";

interface UseTasksOptions {
  enabled: boolean;
  projectId?: string | null;
  status?: string;
}

export interface TasksState {
  tasks: Task[];
  isLoading: boolean;
  error: Error | null;
  refresh: () => Promise<void>;
  createTask: (data: CreateTaskRequest) => Promise<void>;
  isCreating: boolean;
}

export const useTasks = ({
  enabled,
  projectId,
  status,
}: UseTasksOptions): TasksState => {
  const queryClient = useQueryClient();

  const {
    data: tasks = [],
    error: queryError,
    isFetching,
    isPending,
    refetch,
  } = useQuery<Task[]>({
    queryKey: taskKeys.list({ projectId, status }),
    queryFn: async () => {
      if (!projectId) return [];
      return await listTasks({ projectId, status });
    },
    enabled: enabled && !!projectId,
    staleTime: 5 * 60 * 1000,
  });

  const { mutateAsync: createMutation, isPending: isCreating } = useMutation({
    mutationFn: createTask,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: taskKeys.lists() }),
  });

  const isLoading = enabled ? isPending || isFetching : false;
  const error = queryError instanceof Error ? queryError : null;

  const refresh = useCallback(async () => {
    await refetch();
  }, [refetch]);

  return useMemo(
    () => ({
      tasks,
      isLoading,
      error,
      refresh,
      createTask: async (data) => { await createMutation(data); },
      isCreating,
    }),
    [tasks, isLoading, error, refresh, createMutation, isCreating]
  );
};
```

### Optimistic Updates

```tsx
const { mutate } = useMutation({
  mutationFn: updateTask,
  onMutate: async (updated) => {
    await queryClient.cancelQueries({ queryKey: taskKeys.lists() });
    const previous = queryClient.getQueryData(taskKeys.list(filters));

    queryClient.setQueryData(taskKeys.list(filters), (old: Task[]) =>
      old.map(t => t.id === updated.id ? { ...t, ...updated } : t)
    );

    return { previous };
  },
  onError: (_err, _updated, context) => {
    queryClient.setQueryData(taskKeys.list(filters), context?.previous);
  },
  onSettled: () => {
    queryClient.invalidateQueries({ queryKey: taskKeys.lists() });
  },
});
```

### Cross-Query Cache Invalidation

When the same data is accessed through multiple query patterns, ALL related queries must be invalidated on mutation.

```tsx
// WRONG — only invalidates own query, other views show stale data
onSuccess: () => {
  queryClient.invalidateQueries({ queryKey: ['taskLinks', taskId] });
  // Missing: bulkTaskLinks, task-links-by-project, etc.
},

// RIGHT — invalidate all related query patterns
const invalidateLinkQueries = () => {
  queryClient.invalidateQueries({ queryKey: ['taskLinks', taskId] });
  queryClient.invalidateQueries({ queryKey: ['bulkTaskLinks'] });
  queryClient.invalidateQueries({ queryKey: ['task-links-by-project'] });
};

onSuccess: invalidateLinkQueries,
```

**Signs of this bug:**
- UI doesn't update after save (but data IS saved to backend)
- Need to refresh page to see changes
- Multiple queries fetch same underlying data with different keys

---

## Storage Hook Pattern

Drop-in replacement for `useState` with automatic localStorage persistence.

```tsx
import { useLocalStorageState } from '@/hooks/useLocalStorageState';

// Simple usage — same API as useState
const [filter, setFilter] = useLocalStorageState('task-filter', 'all');

// With type annotation
const [prefs, setPrefs] = useLocalStorageState<UserPrefs>('user-prefs', defaults);

// With custom serialization (for Dates, Maps, etc.)
const [dateRange, setDateRange] = useLocalStorageState('dates', defaultDates, {
  serialize: (value) => JSON.stringify({
    start: value.start.toISOString(),
    end: value.end.toISOString(),
  }),
  deserialize: (str) => {
    const parsed = JSON.parse(str);
    return { start: new Date(parsed.start), end: new Date(parsed.end) };
  },
});
```

### Multi-Key Scoped Storage

```tsx
export const useTaskStorage = (projectKey: string) => {
  const scopedKey = useCallback(
    (base: string) => `${projectKey}__${base}`,
    [projectKey]
  );

  const [completedIds, setCompletedIds] = useLocalStorageState<string[]>(
    scopedKey('completed'), []
  );

  const [expandedSections, setExpandedSections] = useLocalStorageState<Record<string, boolean>>(
    scopedKey('expanded'), {}
  );

  return { completedIds, setCompletedIds, expandedSections, setExpandedSections };
};
```

---

## Zustand Stores (Complex Client State)

For state that's too complex for query hooks — multi-step workflows, cross-component mutations, client-side caching.

```tsx
// features/{feature}/state/{storeName}Store.ts
import { create } from 'zustand';

interface TaskEditorState {
  status: 'idle' | 'loading' | 'loaded' | 'error';
  tasks: Task[];
  selectedId: string | null;
  fetchTasks: (options?: { force?: boolean }) => Promise<Task[]>;
  selectTask: (id: string) => void;
}

let inFlight: Promise<Task[]> | null = null;

export const useTaskEditorStore = create<TaskEditorState>((set, get) => ({
  status: 'idle',
  tasks: [],
  selectedId: null,

  fetchTasks: async ({ force = false } = {}) => {
    if (!force && get().status === 'loaded') return get().tasks;
    if (inFlight) return inFlight;

    set({ status: 'loading' });
    const promise = fetchTasksAPI()
      .then((tasks) => { set({ status: 'loaded', tasks }); return tasks; })
      .catch((err) => { set({ status: 'error' }); throw err; })
      .finally(() => { inFlight = null; });
    inFlight = promise;
    return promise;
  },

  selectTask: (id) => set({ selectedId: id }),
}));

// Always export a reset function for cleanup (logout, navigation, etc.)
export const resetTaskEditorStore = () => {
  inFlight = null;
  useTaskEditorStore.setState({ status: 'idle', tasks: [], selectedId: null });
};
```

### When Zustand vs Query Hooks

| Scenario | Use |
|----------|-----|
| Fetch a list/detail and cache it | Query hooks |
| CRUD with cache invalidation | Query hooks |
| Multi-step client workflow with intermediate state | Zustand |
| State shared across many components without prop drilling | Zustand |
| Complex derived state or computed values | Zustand |

**Anti-pattern:** Don't replicate query hook loading/error/caching in a Zustand store when all you need is fetch-and-display.

---

## Common Composite Patterns

### Async Data Widget

The most common pattern. Every async component MUST handle all four states.

```tsx
import { useQuery } from '@tanstack/react-query';

export const TasksWidget = () => {
  const { data: tasks = [], isPending, error, refetch } = useQuery({
    queryKey: ['tasks'],
    queryFn: fetchTasks,
  });

  if (isPending) return <LoadingState message="Loading tasks..." />;
  if (error)     return <ErrorState message={error.message} onRetry={refetch} />;
  if (!tasks.length) return <EmptyState message="No tasks yet" action={<Button>Create</Button>} />;

  return (
    <Panel tone="default" padding="md">
      <Toolbar
        start={<SectionHeading>Tasks</SectionHeading>}
        end={<Button size="sm">Add</Button>}
        bordered
      />
      <div className="mt-4 space-y-2">
        {tasks.map(task => <TaskCard key={task.id} {...task} />)}
      </div>
    </Panel>
  );
};
```

### Filterable List Widget

```tsx
export const FilterableWidget = () => {
  const [filter, setFilter] = useLocalStorageState('task-filter', 'all');
  const { data: items = [] } = useQuery({ queryKey: ['items'], queryFn: fetchItems });

  const filtered = useMemo(() =>
    items.filter(item => filterFn(item, filter)),
    [items, filter]
  );

  return (
    <Panel tone="default" padding="md">
      <Toolbar
        start={<SectionHeading>Items</SectionHeading>}
        end={
          <ChipGroup
            options={[
              { id: 'all', label: 'All' },
              { id: 'active', label: 'Active' },
              { id: 'done', label: 'Done' },
            ]}
            value={filter}
            onChange={setFilter}
          />
        }
        bordered
      />
      {filtered.length === 0 ? (
        <EmptyState message="No items match filter" />
      ) : (
        <div className="mt-4 space-y-2">
          {filtered.map(item => <ItemCard key={item.id} {...item} />)}
        </div>
      )}
    </Panel>
  );
};
```

### Nested Panel Layout

```tsx
<Panel tone="default" padding="lg">
  <SectionHeading>Parent Section</SectionHeading>

  <div className="mt-4 space-y-3">
    <Panel tone="muted" padding="md">
      {/* Subsection 1 */}
    </Panel>

    <Panel tone="muted" padding="md">
      {/* Subsection 2 */}
    </Panel>
  </div>
</Panel>
```

### Dashboard Widget with Shell

When widgets are displayed in a dashboard grid (masonry, flexbox, etc.), wrap them in WidgetShell to get expand/collapse, width control, and layout persistence.

```tsx
export const TasksWidget = () => {
  return (
    <WidgetShell id="tasks" title="Tasks" hideHeader hideExpandToggle>
      {({ expanded, widthStep, maxWidthStep, setExpanded, setWidthStep }) => (
        <div className="space-y-4">
          {/* Custom header using Toolbar or BistroHeader */}
          <Toolbar
            start={<SectionHeading>Tasks</SectionHeading>}
            end={<Button size="sm">Add</Button>}
            bordered
          />

          {/* Content — can vary based on expanded state */}
          {expanded ? (
            <ExpandedTaskView />
          ) : (
            <CompactTaskView />
          )}
        </div>
      )}
    </WidgetShell>
  );
};
```

### Fullscreen Widget

Widget with optional fullscreen expansion mode.

```tsx
export const MyWidget = () => {
  const [isFullscreen, setIsFullscreen] = useState(false);

  return (
    <>
      {/* Fullscreen overlay */}
      <FullscreenSurface
        open={isFullscreen}
        onClose={() => setIsFullscreen(false)}
        tone="white"
      >
        <FullscreenHeader
          title="My Widget"
          onClose={() => setIsFullscreen(false)}
        />
        <div className="flex-1 min-h-0 overflow-auto p-4">
          {/* Full content */}
        </div>
      </FullscreenSurface>

      {/* Normal widget */}
      <WidgetShell id="my-widget" title="My Widget" hideHeader hideExpandToggle>
        {({ expanded, setExpanded, widthStep, maxWidthStep, setWidthStep }) => (
          <div className="space-y-3">
            <Toolbar
              start={<SectionHeading>My Widget</SectionHeading>}
              end={
                <FullscreenToggle onEnter={() => setIsFullscreen(true)} />
              }
              bordered
            />
            {expanded && <div className="space-y-2">{/* Content */}</div>}
          </div>
        )}
      </WidgetShell>
    </>
  );
};
```

### Role-Based Widget Extension

When a widget serves multiple user roles, extend it with role props rather than creating separate components.

```tsx
// WRONG: Creating AdminTaskList.tsx when TaskList.tsx already exists
// RIGHT: Adding role-based behavior to TaskList.tsx

export const TaskList: React.FC<{
  role?: "user" | "admin";
  projectId?: string;
}> = ({ role, projectId }) => {
  const isAdmin = role === "admin" && !!projectId;

  // Fetch additional data for admins
  const adminQuery = useQuery({
    queryKey: ["admin-task-meta", projectId],
    queryFn: () => getAdminMeta(projectId!),
    enabled: isAdmin,
  });

  return (
    <TaskCard
      onBulkAction={isAdmin ? handleBulkAction : undefined}
      showMetrics={isAdmin}
    />
  );
};
```

---

## Anti-Patterns — WRONG vs RIGHT

### Inline Panel Styling
```tsx
// WRONG
<div className="rounded-xl border border-gray-200 bg-white shadow-lg p-4">

// RIGHT
<Panel tone="default" padding="md">
```

### Inline Loading States
```tsx
// WRONG
{isPending && (
  <div className="flex items-center justify-center p-8">
    <Loader2 className="w-6 h-6 animate-spin" />
    Loading...
  </div>
)}

// RIGHT
{isPending && <LoadingState message="Loading..." />}
```

### Custom Buttons
```tsx
// WRONG
<button className="px-3 py-2 bg-blue-500 text-white rounded-md">
  Save
</button>

// RIGHT
<Button tone="primary">Save</Button>
```

### Custom Error Displays
```tsx
// WRONG
{error && (
  <div className="rounded-xl border border-red-200 bg-red-50 p-6">
    <p className="text-red-700">{error.message}</p>
    <button onClick={refetch}>Try Again</button>
  </div>
)}

// RIGHT
{error && <ErrorState message={error.message} onRetry={refetch} />}
```

### Manual Loading/Error State (Reinventing Query Hooks)
```tsx
// WRONG — 15+ lines of boilerplate
const [data, setData] = useState([]);
const [isLoading, setIsLoading] = useState(false);
const [error, setError] = useState(null);

useEffect(() => {
  setIsLoading(true);
  fetchData()
    .then(setData)
    .catch(setError)
    .finally(() => setIsLoading(false));
}, []);

// RIGHT — 5 lines
const { data = [], isPending, error, refetch } = useQuery({
  queryKey: ['data'],
  queryFn: fetchData,
});
```

### Manual localStorage
```tsx
// WRONG — 8 lines, no error handling, no SSR safety
const [value, setValue] = useState(() => {
  const stored = localStorage.getItem('key');
  return stored ? JSON.parse(stored) : defaultValue;
});
useEffect(() => { localStorage.setItem('key', JSON.stringify(value)); }, [value]);

// RIGHT — 1 line
const [value, setValue] = useLocalStorageState('key', defaultValue);
```

### Missing Query Key Dependencies
```tsx
// WRONG — stale data when projectId changes
const { data } = useQuery({
  queryKey: ['tasks'],              // Missing projectId!
  queryFn: () => fetchTasks(projectId),
});

// RIGHT — include all dependencies
const { data } = useQuery({
  queryKey: ['tasks', projectId],   // Refetches when projectId changes
  queryFn: () => fetchTasks(projectId),
  enabled: !!projectId,
});
```

### Not Using enabled Flag
```tsx
// WRONG — fetches with undefined id, API errors
const { data } = useQuery({
  queryKey: ['task', taskId],
  queryFn: () => fetchTask(taskId!),  // Dangerous non-null assertion
});

// RIGHT — wait for valid id
const { data } = useQuery({
  queryKey: ['task', taskId],
  queryFn: () => fetchTask(taskId!),
  enabled: !!taskId,                  // Only fetch when taskId exists
});
```

### Custom Locked/Gated Content
```tsx
// WRONG — inline locked content styling
<div className="flex items-center gap-2">
  <Lock size={16} />
  <span>Purchase to unlock</span>
  <button>Buy Now</button>
</div>

// RIGHT
<LockedState
  title="Premium Content"
  message="Purchase to unlock"
  action={<Button>Buy Now</Button>}
/>
```

### Missing Async States
```tsx
// WRONG — only handles success case
export const TasksWidget = () => {
  const { data: tasks = [] } = useQuery({ ... });
  return <div>{tasks.map(t => <TaskCard key={t.id} {...t} />)}</div>;
};

// RIGHT — handles ALL four states
export const TasksWidget = () => {
  const { data: tasks = [], isPending, error, refetch } = useQuery({ ... });

  if (isPending)     return <LoadingState message="Loading tasks..." />;
  if (error)         return <ErrorState message={error.message} onRetry={refetch} />;
  if (!tasks.length) return <EmptyState message="No tasks yet" />;

  return <div>{tasks.map(t => <TaskCard key={t.id} {...t} />)}</div>;
};
```

---

## Refactoring Workflow

Every refactoring task follows this 3-phase process:

### Phase 1: Identify Low-Hanging Fruit

1. Read the target component
2. Identify:
   - Repeated JSX patterns (3+ occurrences)
   - Inline styles that should use library primitives
   - Manual useState/useEffect for data fetching (should use query hooks)
   - Manual localStorage logic (should use storage hook)
   - Utility functions that could be extracted
3. Note component size (flag if >300 LOC)

### Phase 2: Make the Plan

Document extraction strategy before changing code:
- Current state (LOC, complexity)
- Extraction targets (what to extract)
- Target state (expected LOC reduction)
- Order of operations (what to do first)
- Risk assessment

### Phase 3: Execute Incrementally

For each extraction:
1. Extract component/hook/utility
2. Add tests if applicable
3. Verify build passes
4. Verify type check passes
5. Commit with descriptive message

---

## Authentication Pattern

### Auth Context

```tsx
import { useAuth } from '@/contexts/AuthContext';

const { user, role, isAuthenticated, isLoading } = useAuth();
// role: 'user' | 'admin' | 'unknown' (replace with your project's roles)
```

### Protected Routes

```tsx
// Only authenticated users
<Route element={<ProtectedRoute />}>
  <Route path="/app" element={<Dashboard />} />
</Route>

// Role-restricted
<Route element={<ProtectedRoute allowRoles={['admin']} />}>
  <Route path="/admin/*" element={<AdminPanel />} />
</Route>
```

### Route Conventions

| Prefix | Audience | Example |
|--------|----------|---------|
| `/` | Public (SEO, marketing) | `/`, `/articles`, `/pricing` |
| `/auth` | Auth flow | `/auth`, `/auth/callback` |
| `/app` | Authenticated users | `/app`, `/app/settings` |
| `/admin` | Admin-only | `/admin/users`, `/admin/reports` |

---

## Type Conventions

- **Backend response types:** Prefix with `Raw` (e.g., `RawTask`) — snake_case fields matching API
- **Frontend types:** PascalCase, camelCase fields (e.g., `Task`) — mapped from Raw types
- **Status unions:** `type Status = 'idle' | 'loading' | 'loaded' | 'error'`
- **Error code unions:** `type ErrorCode = 'NOT_FOUND' | 'ALREADY_EXISTS' | 'NO_ACCESS'`
- **Feature types:** Colocate in `features/{feature}/types/` or `features/{feature}/api/types.ts`
- **Cross-feature types:** Put in `src/types/` and re-export from `src/types/index.ts`
- **No `any`** — Use `unknown` if the type is truly unknown, then narrow

---

## Design Tokens

> **Replace these values** with your project's actual design tokens.
> The point is: document your color/font/animation system so the scaffolder uses it consistently.

### Colors (Example — Tailwind custom classes)

| Token | Use |
|-------|-----|
| `brand-primary` | Main accent, CTAs, active states |
| `brand-muted` | Borders, muted text, dividers |
| `brand-text` | Primary text |
| `brand-text-secondary` | Secondary text |
| `brand-background` | Page backgrounds |
| `brand-surface` | Card/panel backgrounds |

### Multiple Color Contexts

If the project has different visual zones (e.g., dark navigation shell + light content panels, dark mode + light mode), document which tokens to use in each zone. **This is a common source of invisible text/borders.**

```
WRONG: Using dark-theme text token (rgba white) inside a light panel → invisible
RIGHT: Using light-mode text token (dark ink with opacity) inside a light panel → visible
```

For each token, note the **rendering context** it was designed for. If a token only works on dark backgrounds, mark it explicitly so the scaffolder doesn't use it in light content areas.

### Fonts (Example — Tailwind font classes)

| Class | Use |
|-------|-----|
| `font-sans` / `font-body` | Body text (default) |
| `font-display` | Headings, hero text |
| `font-mono` | Code, technical content |

### Animations (Example)

| Class | Duration | Use |
|-------|----------|-----|
| `animate-tab-pop` | 200ms | Tab selection feedback |
| `animate-fade-in` | 150ms | Element entrance |

---

## Testing

### Framework

Use the project's test runner (vitest, jest, etc.) + @testing-library/react for component tests.

### Test Structure

```tsx
import { describe, it, expect, vi } from 'vitest'; // or jest
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

describe('MyComponent', () => {
  it('renders correctly', () => {
    render(<MyComponent />);
    expect(screen.getByText('Expected Text')).toBeInTheDocument();
  });

  it('handles user interaction', async () => {
    const user = userEvent.setup();
    const onAction = vi.fn();
    render(<MyComponent onAction={onAction} />);

    await user.click(screen.getByRole('button', { name: 'Submit' }));
    expect(onAction).toHaveBeenCalledOnce();
  });
});
```

### Hook Testing

```tsx
import { renderHook, act } from '@testing-library/react';

describe('useMyHook', () => {
  it('returns initial state', () => {
    const { result } = renderHook(() => useMyHook());
    expect(result.current.value).toBe(defaultValue);
  });

  it('updates on action', async () => {
    const { result } = renderHook(() => useMyHook());
    await act(async () => {
      result.current.doThing();
    });
    expect(result.current.value).toBe(newValue);
  });
});
```

### Test File Locations

```
src/hooks/__tests__/useMyHook.test.ts           # Shared hooks
src/features/{feature}/hooks/__tests__/          # Feature hooks
src/features/{feature}/__tests__/                # Feature-level tests
src/components/__tests__/MyComponent.test.tsx    # Shared components
```

---

## Hook Naming Conventions

- `use{DataName}` — Fetch/manage data (useTasks, useProjects)
- `use{ComponentName}State` — Component-specific state (useCardState)
- `use{ActionVerb}` — Action-oriented (useAutoFocus, useToggle)
- `use{Domain}{Action}` — Domain + action (useTaskActions, useProjectMetrics)

---

## Validation Checklist

Before completing any component work, verify:

### Component Library Primitives
- [ ] No inline panel/card styling (use Panel primitive)
- [ ] No inline button styling (use Button primitive)
- [ ] No manual spinners/loaders (use LoadingState primitive)
- [ ] No manual error displays (use ErrorState primitive with onRetry)
- [ ] No inline locked/gated content (use LockedState primitive)
- [ ] Dashboard widgets wrapped in WidgetShell (if applicable)

### Data Fetching & State
- [ ] No manual useState for loading/error/data (use query hooks)
- [ ] No manual localStorage.getItem/setItem (use storage hook)
- [ ] Query keys include all dependencies
- [ ] Mutations invalidate all related query keys

### Async States
- [ ] Loading state handled (isPending check)
- [ ] Error state handled (error check with retry)
- [ ] Empty state handled (empty array/null check)
- [ ] Success state renders data

### Type Safety
- [ ] Types match shared.md exactly — no `any`
- [ ] Props interfaces defined
- [ ] Backend types prefixed with `Raw` (snake_case), frontend types in camelCase

### Code Quality
- [ ] Components under 300 LOC preferred, under 400 absolute max
- [ ] Build passes
- [ ] Type check passes
- [ ] Tests pass (if applicable)

---

## Source of Truth

**The code is always the source of truth** — not this document, not docs, not plans.

If you find discrepancies between documentation and code:
1. **Verify what the code actually does** before implementing anything
2. **Follow the code's patterns**, not what docs say the patterns should be
3. If unsure, check real implementations in `src/features/` for how things actually work

Fix stale docs opportunistically when you encounter them, but never go hunting for documentation problems.
