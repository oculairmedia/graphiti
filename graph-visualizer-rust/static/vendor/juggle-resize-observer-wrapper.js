// Wrapper for @juggle/resize-observer to make it work with ES modules
import { ResizeObserver as ResizeObserverImpl } from '/vendor/juggle-resize-observer/lib/ResizeObserver.js';
import { ResizeObserverEntry } from '/vendor/juggle-resize-observer/lib/ResizeObserverEntry.js';
import { ResizeObserverSize } from '/vendor/juggle-resize-observer/lib/ResizeObserverSize.js';

export { ResizeObserverImpl as ResizeObserver, ResizeObserverEntry, ResizeObserverSize };