import { useCallback, useRef } from 'react';

/**
 * Hook that debounces a callback function
 * PERFORMANCE: Use this for expensive operations like config updates
 * 
 * @param callback - The function to debounce
 * @param delay - Debounce delay in milliseconds
 * @returns Debounced version of the callback
 */
export function useDebouncedCallback<T extends (...args: any[]) => any>(
  callback: T,
  delay: number
): (...args: Parameters<T>) => void {
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);
  const callbackRef = useRef(callback);
  
  // Update callback ref when it changes
  callbackRef.current = callback;
  
  return useCallback(
    (...args: Parameters<T>) => {
      // Clear existing timeout
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      
      // Set new timeout
      timeoutRef.current = setTimeout(() => {
        callbackRef.current(...args);
      }, delay);
    },
    [delay]
  );
}
