import React, { memo, useRef, useEffect } from 'react';

/**
 * StableCosmographWrapper - Prevents Cosmograph from re-initializing
 * 
 * This wrapper uses React.memo with a custom comparison function to prevent
 * unnecessary re-renders that can cause Cosmograph to lose its WebGL context
 * and throw "missing buffer for attribute 'pointIndices'" errors.
 */
interface StableCosmographWrapperProps {
  children: React.ReactElement;
  nodes: any[];
  links: any[];
}

export const StableCosmographWrapper = memo<StableCosmographWrapperProps>(
  ({ children }) => {
    // Simply pass through the children without modification
    // The memo wrapper prevents re-renders unless props actually change
    return children;
  },
  (prevProps, nextProps) => {
    // Custom comparison function to prevent re-renders
    // Only re-render if the actual data changes (by reference for performance)
    
    // Check if nodes array reference changed
    const nodesChanged = prevProps.nodes !== nextProps.nodes;
    
    // Check if links array reference changed
    const linksChanged = prevProps.links !== nextProps.links;
    
    // Check if the child component itself changed (unlikely but possible)
    const childChanged = prevProps.children !== nextProps.children;
    
    // Return true to prevent re-render, false to allow it
    // We prevent re-render if nothing changed
    return !nodesChanged && !linksChanged && !childChanged;
  }
);

StableCosmographWrapper.displayName = 'StableCosmographWrapper';

/**
 * useStableRef - Hook to maintain stable references across renders
 * 
 * This hook ensures that refs don't change between renders unless the
 * actual value changes, preventing unnecessary re-renders in child components.
 */
export function useStableRef<T>(value: T): React.MutableRefObject<T> {
  const ref = useRef(value);
  
  useEffect(() => {
    ref.current = value;
  }, [value]);
  
  return ref;
}

/**
 * useStableCallback - Hook to maintain stable callback references
 * 
 * This hook ensures callbacks don't change between renders unless their
 * dependencies change, preventing unnecessary re-renders.
 */
export function useStableCallback<T extends (...args: any[]) => any>(
  callback: T,
  deps: React.DependencyList
): T {
  const callbackRef = useRef(callback);
  
  useEffect(() => {
    callbackRef.current = callback;
  }, deps);
  
  // Return a stable function that calls the current callback
  const stableCallback = useRef(
    ((...args: any[]) => callbackRef.current(...args)) as T
  );
  
  return stableCallback.current;
}

/**
 * CosmographGuard - Component that protects Cosmograph from wrapper re-renders
 * 
 * This component creates a render boundary that prevents parent re-renders
 * from propagating to Cosmograph unless the data actually changes.
 */
export const CosmographGuard: React.FC<{
  children: React.ReactNode;
  dataVersion?: number | string;
}> = memo(
  ({ children }) => {
    return <>{children}</>;
  },
  (prevProps, nextProps) => {
    // Only re-render if dataVersion changes
    return prevProps.dataVersion === nextProps.dataVersion;
  }
);

CosmographGuard.displayName = 'CosmographGuard';