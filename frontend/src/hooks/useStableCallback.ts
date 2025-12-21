import { useRef, useLayoutEffect, useCallback } from 'react';

/**
 * Returns a stable callback that always has access to the latest values
 * but maintains the same reference across renders to prevent re-renders
 * in child components.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function useStableCallback<T extends (...args: any[]) => any>(callback: T): T {
  const callbackRef = useRef(callback);
  
  // Update the ref on every render so it always has the latest callback
  useLayoutEffect(() => {
    callbackRef.current = callback;
  });
  
  // Return a stable callback that calls the latest version
  return useCallback((...args: Parameters<T>) => {
    return callbackRef.current(...args);
  }, []) as T;
}