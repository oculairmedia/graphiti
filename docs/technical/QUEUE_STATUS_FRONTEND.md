## Queue Status UI (Frontend)

This document explains where the Queue Status UI lives in the frontend, how it fetches its data, and the backend endpoints involved.

### Where it is used

- Component: QueryControlsTab (renders the "Queue Status" panel)
- Path: frontend/src/components/ControlPanel/QueryControlsTab.tsx

The panel displays:
- Current status string (e.g., processing, idle)
- Pending (visible_messages)
- Processing (invisible_messages)
- Success rate (when total_processed > 0)

Relevant rendering excerpt:

```tsx
// QueryControlsTab.tsx
<Badge
  variant={queueStatus.status === 'processing' ? 'default' : 'secondary'}
  className={`text-xs h-5 ${
    queueStatus.status === 'processing' ? 'bg-green-500/20 text-green-400 border-green-500/30' :
    queueStatus.status === 'idle' ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' :
    'bg-gray-500/20 text-gray-400 border-gray-500/30'
  }`}
>
  {queueStatus.status}
</Badge>
```

### How data is fetched (hook)

- Hook: useQueueStatus
- Path: frontend/src/hooks/useQueueStatus.ts

Behavior (current implementation):
- Fetches queue status on mount and every refreshInterval ms (default 5000 ms)
- Exposes { queueStatus, isLoading, isRefreshing, error, refresh }
- isLoading is initial-only; isRefreshing indicates background refetches
- Uses an inFlightRef to avoid overlapping requests; preserves previous data on errors
- Can be disabled via { enabled: false }

Key code (simplified snapshot):

```ts
// frontend/src/hooks/useQueueStatus.ts
interface UseQueueStatusResult {
  queueStatus: QueueStatus | null;
  isLoading: boolean;      // initial-only
  isRefreshing: boolean;   // background refetches
  error: string | null;
  refresh: () => void;
}

export const useQueueStatus = ({ refreshInterval = 5000, enabled = true } = {}): UseQueueStatusResult => {
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlightRef = useRef(false);
  const graphClient = new GraphClient();

  const fetchQueueStatus = async () => {
    if (!enabled || inFlightRef.current) return;
    inFlightRef.current = true;
    const isInitial = queueStatus === null;
    try {
      if (isInitial) setIsLoading(true); else setIsRefreshing(true);
      setError(null);
      const status = await graphClient.getQueueStatus();
      setQueueStatus(prev => (JSON.stringify(prev) === JSON.stringify(status) ? prev : status));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch queue status');
    } finally {
      if (isInitial) setIsLoading(false);
      setIsRefreshing(false);
      inFlightRef.current = false;
    }
  };

  useEffect(() => {
    if (!enabled) return;
    fetchQueueStatus();
    const interval = setInterval(fetchQueueStatus, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval, enabled]);

  return { queueStatus, isLoading, isRefreshing, error, refresh: fetchQueueStatus };
};
```

### Frontend API client

- Class: GraphClient
- Path: frontend/src/api/graphClient.ts
- Base URL: '/api'

Method used:

```ts
async getQueueStatus(): Promise<QueueStatus> {
  return this.fetchWithError<QueueStatus>(`${this.baseUrl}/queue/status`);
}
```

Response type on the frontend:

- Path: frontend/src/api/types.ts

```ts
export interface QueueStatus {
  status: string;
  visible_messages: number;
  invisible_messages: number;
  total_processed: number;
  total_failed: number;
  success_rate: number;
  last_updated: string;
}
```

### Backend route the frontend calls

- Service: Rust API (graph-visualizer-rust)
- Route registered: GET /api/queue/status
- Path: graph-visualizer-rust/src/main.rs

Handler summary (get_queue_status):
- Reads QUEUE_URL env var (default http://graphiti-queued:8080)
- Uses queue name "ingestion"
- Calls the Queued service at GET {QUEUE_URL}/queue/{queue_name}/metrics
- Maps metrics into the QueueStatus JSON returned to the frontend

```rust
// main.rs
.route("/api/queue/status", get(get_queue_status))
```

Notes:
- This is distinct from the Python FastAPI router under server/graph_service/routers/ingest_queue.py, which also exposes queue-related endpoints (e.g., /queue/stats). The frontend's GraphClient is currently wired to the Rust route (/api/queue/status).

### Related (but different) UI: Offline WebSocket queue

- Component: WebSocketMonitor (shows offline client-side message queue state)
- Path: frontend/src/components/WebSocketMonitor.tsx
- Source of data: EnhancedWebSocketProvider + OfflineQueueManager
- This reflects browser-side queued websocket messages (e.g., when offline) and is not the same as the server ingestion queue.

```tsx
// WebSocketMonitor.tsx excerpt
<Badge variant={queueStatus.queueSize > 0 ? 'warning' : 'secondary'}>
  {queueStatus.queueSize} messages
</Badge>
```

### Customizing/Using elsewhere

- To change refresh rate: useQueueStatus({ refreshInterval: 10000 })
- To temporarily disable polling (e.g., when panel is hidden): useQueueStatus({ enabled: false })
- For reuse: you can extract the QueryControlsTab queue section into a dedicated <QueueStatusPanel /> component that consumes the same hook.

### Quick reference: File paths

- Frontend UI: frontend/src/components/ControlPanel/QueryControlsTab.tsx
- Hook: frontend/src/hooks/useQueueStatus.ts
- Frontend client: frontend/src/api/graphClient.ts
- Types: frontend/src/api/types.ts
- Backend (Rust) route: graph-visualizer-rust/src/main.rs (/api/queue/status)
- Queue service metrics endpoint: queued/queued/src/main.rs (/queue/:queue/metrics)
- Related offline UI: frontend/src/components/WebSocketMonitor.tsx




## Visual Flicker and Animation Hitch: Analysis and Fix

### Problem summary
- Users see the entire Queue Status block disappear and reappear on each periodic refresh (flicker).
- Root cause: the hook sets `isLoading=true` on every fetch; the UI hides the whole content when `isLoading` is true and shows a “Loading…” placeholder, causing layout teardown/rebuild.

### Root cause details
- Hook (current):
  - Calls `setIsLoading(true)` for every poll, not just the initial load.
  - After fetch, toggles `setIsLoading(false)`.
- UI (current):
  - Top-level conditional: `queueLoading ? Loading... : Content`.
  - When `queueLoading` toggles to true during refresh, the content is removed and the placeholder is shown, then content re-mounts → flicker/layout shift.

### Goals for the fix
- Keep last known data visible during background refreshes.
- Use a subtle inline indicator for refresh state (spinner), not a full content swap.
- Show a skeleton only on the first load (when no data yet).
- Avoid layout shifts; maintain stable heights.

### Recommended implementation (no new deps)

1) Update the hook to separate initial load from background refreshes
- Add `isRefreshing` for subsequent refetches.
- Keep `isLoading` only for the very first fetch (when `queueStatus === null`).
- Prevent overlapping requests with an `inFlightRef`.
- Preserve previous data on errors (do not clear `queueStatus`).

Example (drop-in replacement in `frontend/src/hooks/useQueueStatus.ts`):

```ts
import { useState, useEffect, useRef } from 'react';
import { QueueStatus } from '@/api/types';
import { graphClient as graphClientSingleton } from '@/api/graphClient';

interface UseQueueStatusOptions { refreshInterval?: number; enabled?: boolean; }
interface UseQueueStatusResult {
  queueStatus: QueueStatus | null;
  isLoading: boolean;      // initial-only
  isRefreshing: boolean;   // background refetches
  error: string | null;
  refresh: () => void;
}

export const useQueueStatus = ({ refreshInterval = 5000, enabled = true }: UseQueueStatusOptions = {}): UseQueueStatusResult => {
  const [queueStatus, setQueueStatus] = useState<QueueStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inFlightRef = useRef(false);
  const graphClient = graphClientSingleton;

  const fetchQueueStatus = async () => {
    if (!enabled || inFlightRef.current) return;
    inFlightRef.current = true;
    const initial = queueStatus === null;
    if (initial) setIsLoading(true); else setIsRefreshing(true);
    try {
      setError(null);
      const status = await graphClient.getQueueStatus();
      setQueueStatus(prev => (JSON.stringify(prev) === JSON.stringify(status) ? prev : status));
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to fetch queue status';
      setError(msg); // keep showing last good data
    } finally {
      if (initial) setIsLoading(false);
      setIsRefreshing(false);
      inFlightRef.current = false;
    }
  };

  const refresh = () => { fetchQueueStatus(); };

  useEffect(() => {
    if (!enabled) return;
    fetchQueueStatus();
    const interval = setInterval(fetchQueueStatus, refreshInterval);
    return () => clearInterval(interval);
  }, [refreshInterval, enabled]);

  return { queueStatus, isLoading, isRefreshing, error, refresh };
};
```

2) Update the UI to keep content mounted and show a subtle inline refresh state
- Replace the top-level `queueLoading` conditional with a skeleton only for the initial load: `showSkeleton = isLoading && !queueStatus`.
- Show a small inline spinner (e.g., `Loader2`) next to the Status label when `isRefreshing`.
- Keep rendering the last known data during refresh or transient errors.
- Add small transitions to number/value changes to reduce jank.

Example (edits in `frontend/src/components/ControlPanel/QueryControlsTab.tsx`):

```tsx
import { Activity, Loader2 } from 'lucide-react';
// ...
const { queueStatus, isLoading, isRefreshing, error } = useQueueStatus({ refreshInterval: 5000 });
const showSkeleton = isLoading && !queueStatus;

<CardContent className="space-y-2">
  {showSkeleton ? (
    // Initial-only skeleton matching final layout heights
    <div className="space-y-2">
      <div className="h-5 w-24 bg-muted/30 rounded animate-pulse" />
      <div className="grid grid-cols-2 gap-2">
        <div className="h-4 bg-muted/30 rounded animate-pulse" />
        <div className="h-4 bg-muted/30 rounded animate-pulse" />
      </div>
    </div>
  ) : queueStatus ? (
    <div className="space-y-2">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Status</span>
          {isRefreshing && <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" />}
        </div>
        <Badge
          variant={queueStatus.status === 'processing' ? 'default' : 'secondary'}
          className={`text-xs h-5 transition-colors duration-200 ${
            queueStatus.status === 'processing' ? 'bg-green-500/20 text-green-400 border-green-500/30' :
            queueStatus.status === 'idle' ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' :
            'bg-gray-500/20 text-gray-400 border-gray-500/30'
          }`}
        >
          {queueStatus.status}
        </Badge>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Pending</span>
          <span className="text-primary font-mono transition-opacity duration-200">{queueStatus.visible_messages}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Processing</span>
          <span className="text-primary font-mono transition-opacity duration-200">{queueStatus.invisible_messages}</span>
        </div>
      </div>

      {queueStatus.total_processed > 0 && (
        <div className="flex justify-between items-center text-xs">
          <span className="text-muted-foreground">Success Rate</span>
          <Badge
            variant="outline"
            className={`text-xs h-5 transition-colors duration-200 ${
              queueStatus.success_rate >= 95 ? 'text-green-400 border-green-500/30' :
              queueStatus.success_rate >= 80 ? 'text-yellow-400 border-yellow-500/30' :
              'text-red-400 border-red-500/30'
            }`}
          >
            {queueStatus.success_rate.toFixed(0)}%
          </Badge>
        </div>
      )}

      {error && (
        <div className="text-[10px] text-amber-400">Connection issue; showing last update</div>
      )}
    </div>
  ) : (
    <div className="text-xs text-muted-foreground">No queue data available</div>
  )}
</CardContent>
```

### UX and animation notes
- Maintain stable container height to prevent layout jumps. Skeletons should match the final layout dimensions.
- Use `transition-opacity duration-200` (or `motion-safe:transition-all`) on changing values for smoother updates.
- Keep numbers monospaced (`font-mono`) to reduce width changes.
- Prefer subtle inline indicators (small spinner) to full-content placeholders for refreshes.
- On transient refresh errors, keep last known data and show a small hint instead of clearing the panel.

### Optional alternative: TanStack Query
- Replace the custom polling with `@tanstack/react-query`:
  - `useQuery(['queue-status'], fetcher, { refetchInterval: 5000, keepPreviousData: true, staleTime: 4000 })`
  - Use `isLoading` for initial skeleton; `isFetching` for inline spinner.
- Benefits: caching, deduping, retry backoff, SWR behavior baked in.
- Tradeoff: adds a dependency and requires a minor refactor.

### Validation checklist (to prevent animation hitch)
- During refresh, the content remains mounted; only a small spinner indicates activity.
- No container height changes between states (initial skeleton is the only exception).
- Numeric updates fade smoothly without jarring color or layout jumps.
- Errors during refresh do not wipe content; last good state is visible.



## Production Hardening and Meta-Style Standards

### Code Quality & Architecture
- Abortability and stale updates:
  - Prefer AbortController end-to-end so in-flight fetches can be canceled on unmount or when a new fetch starts.
  - If GraphClient cannot accept an external signal yet, add a requestId guard and mountedRef; only apply results from the latest requestId and when mounted/enabled.
- Adaptive polling:
  - Replace setInterval with a setTimeout loop that schedules the next poll only after the previous completes; add small jitter (±10%) to avoid synchronized bursts across instances.
- Equality check:
  - Replace JSON.stringify deep-compare with field-wise comparison for the fields rendered (status, visible_messages, invisible_messages, total_processed, total_failed, success_rate, last_updated) to avoid allocations and improve clarity.
- Shared data layer:
  - If multiple components consume queue status, centralize via TanStack Query (keepPreviousData, staleTime) or a lightweight context/shared singleton poller to dedupe network calls and simplify state.

### UX and Accessibility
- Stabilize layout:
  - Ensure skeleton height matches final layout; consider a min-height on the container to eliminate micro-shifts.
- Inline activity indication:
  - Use a small inline spinner during isRefreshing; add aria-hidden for decorative spinner or role="status" aria-live="polite" if you intend to announce, but avoid spam.
- Reduced motion:
  - Use motion-safe transitions; keep transitions short (150–200ms). Provide monotonic value updates without dramatic animations.
- Staleness signal:
  - Track lastSuccessAt in the hook; if the data is older than a threshold (e.g., 30–60s), slightly dim values and show “Updated Xs ago” tooltip to set expectations during network issues.

### Implementation Concerns and Edge Cases
- Unmount/disable during fetch:
  - Guard setState with mountedRef and enabledRef; abort or ignore late responses.
- Long requests vs frequent polling:
  - Use the adaptive loop; optionally only show the spinner if fetch time exceeds ~150ms to reduce visual noise for quick round-trips.
- High-frequency updates:
  - Enforce a reasonable lower bound for refreshInterval (e.g., >= 1500ms) unless there is a strong use case for sub-second polling.

### Documentation Improvements
- Add a state diagram to clarify transitions: Initial (isLoading) → Loaded → Refreshing → ErrorWhileLoaded (keep data; show hint). Document render behavior in each state.
- Explicit tradeoffs:
  - Custom hook vs TanStack Query (caching, dedupe, retries, devtools) vs dependency footprint.
  - setInterval simplicity vs setTimeout with jitter for better control.
  - Equality by fields vs always set state (and rely on memoized subcomponents) vs hash.
- Known limitations:
  - Multiple instances will duplicate polling unless centralized.
  - External abort depends on GraphClient accepting an AbortSignal.
  - Staleness UX requires tracking lastSuccessAt in the hook.

### Production Readiness
- Network instability/backoff:
  - Ensure retries use exponential backoff; consider pausing polling for a short window after N consecutive failures and surface a subtle “auto-retrying” hint while keeping data visible.
- Page visibility / offscreen pause:
  - Pause polling when document.hidden is true; resume on visibilitychange. Optionally pause when panel is offscreen via IntersectionObserver.
- Accessibility and contrast:
  - Verify badge color contrast for both themes; spinner should not steal focus; keep DOM mounted to preserve keyboard focus.
- Scaling:
  - Prefer a shared cache (React Query/SWR) for multi-instance use; fall back to a singleton poller in a context if you want to avoid adding a dependency.

### Concrete Action Items
1) Replace JSON.stringify comparison with explicit field-wise compare before setQueueStatus.
2) Convert setInterval to an adaptive setTimeout loop and add ±10% jitter.
3) Add mountedRef, enabledRef, and requestId; optionally extend GraphClient to accept an external AbortSignal and cancel on unmount/new fetch.
4) Track lastSuccessAt in the hook; expose isStale and updatedAgo for better UX.
5) Pause polling on document.hidden; resume on visibilitychange.
6) Spinner accessibility: aria-hidden for decorative spinner; ensure prefers-reduced-motion is respected.
7) Add tests for: initial load skeleton only, no flicker during refresh, no state after unmount, stale handling, visibility pause.

### Optional Enhanced Examples
- Adaptive polling with jitter (pseudo):
```ts
let timeoutId: ReturnType<typeof setTimeout> | null = null;
const scheduleNext = () => {
  const base = refreshInterval;
  const jitter = base * (Math.random() * 0.2 - 0.1); // ±10%
  timeoutId = setTimeout(tick, Math.max(500, base + jitter));
};
const tick = async () => { await fetchQueueStatus(); if (enabled) scheduleNext(); };
useEffect(() => { if (!enabled) return; tick(); return () => timeoutId && clearTimeout(timeoutId); }, [enabled, refreshInterval]);
```
- Stale indicator fields:
```ts
const [lastSuccessAt, setLastSuccessAt] = useState<number | null>(null);
// on success: setLastSuccessAt(Date.now());
const updatedAgoSec = lastSuccessAt ? Math.floor((Date.now() - lastSuccessAt)/1000) : null;
const isStale = updatedAgoSec !== null && updatedAgoSec > 60;
```
- Field-wise equality:
```ts
const same = prev &&
  prev.status === cur.status &&
  prev.visible_messages === cur.visible_messages &&
  prev.invisible_messages === cur.invisible_messages &&
  prev.total_processed === cur.total_processed &&
  prev.total_failed === cur.total_failed &&
  prev.success_rate === cur.success_rate &&
  prev.last_updated === cur.last_updated;
```
