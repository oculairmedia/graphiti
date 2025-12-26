import React, { Suspense } from 'react';
import { prefetchDNS, preconnect } from 'react-dom';
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ParallelInitProvider } from "@/contexts/ParallelInitProvider";
import { DuckDBProvider } from "@/contexts/DuckDBProvider";
import { RustWebSocketProvider } from "@/contexts/RustWebSocketProvider";
import ErrorBoundary from "./components/ErrorBoundary";
import NotFound from "./pages/NotFound";
import { memoryMonitor } from "@/utils/memoryMonitor";
import { preloadDuckDB } from "@/services/duckdb-lazy-loader";

// PERFORMANCE: Lazy load the Index page (contains GraphViz + Cosmograph)
// This moves ~1MB of D3/Cosmograph code out of the initial bundle
const Index = React.lazy(() => import("./pages/Index"));

// Loading fallback for initial page load
const PageLoader = () => (
  <div className="flex items-center justify-center min-h-screen bg-background">
    <div className="flex flex-col items-center gap-4">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      <p className="text-muted-foreground text-sm">Loading graph visualization...</p>
    </div>
  </div>
);

// Create query client once
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // Consider data fresh for 5 minutes
      gcTime: 10 * 60 * 1000, // Keep in cache for 10 minutes (renamed from cacheTime in v5)
      refetchOnWindowFocus: false, // Don't refetch on window focus
      refetchOnReconnect: false, // Don't refetch on reconnect
      retry: 1, // Retry failed requests only once
      retryDelay: 1000, // 1 second retry delay
    },
  },
});

// Version key for schema changes - bump this when Cosmograph schema changes
const SCHEMA_VERSION = 'v2';
const SCHEMA_VERSION_KEY = 'graphiti_cosmograph_schema_version';

const App = () => {
  // Preload resources for better performance
  React.useEffect(() => {
    // Clear stale DuckDB data if schema version changed
    const storedVersion = localStorage.getItem(SCHEMA_VERSION_KEY);
    if (storedVersion !== SCHEMA_VERSION) {
      console.log(`[App] Schema version changed (${storedVersion} -> ${SCHEMA_VERSION}), clearing DuckDB storage...`);
      // Clear IndexedDB databases related to DuckDB/Cosmograph
      indexedDB.databases().then(databases => {
        databases.forEach(db => {
          if (db.name && (db.name.includes('duckdb') || db.name.includes('cosmograph'))) {
            console.log(`[App] Deleting stale database: ${db.name}`);
            indexedDB.deleteDatabase(db.name);
          }
        });
        localStorage.setItem(SCHEMA_VERSION_KEY, SCHEMA_VERSION);
      }).catch(err => {
        console.warn('[App] Could not enumerate IndexedDB databases:', err);
        // Still set the version to avoid repeated attempts
        localStorage.setItem(SCHEMA_VERSION_KEY, SCHEMA_VERSION);
      });
    }
    
    // PERFORMANCE: Don't clear cache on startup - let it persist for faster loads
    // Cache will be invalidated automatically via TTL or WebSocket updates
    
    // Start preloading data asynchronously (dynamic import to avoid bundle conflict)
    import('@/services/preloader').then(({ preloader }) => {
      if (!preloader.isPreloaded('nodes')) {
        console.log('[App] Starting data preload...');
        preloader.startPreloading();
      }
      // Log preloader stats
      const stats = preloader.getStats();
      console.log('[App] Preloader stats:', stats);
    });
    
    // Start preloading DuckDB in the background
    preloadDuckDB();
    
    // Preconnect to API endpoints if configured
    const apiUrl = import.meta.env.VITE_API_URL;
    if (apiUrl) {
      const url = new URL(apiUrl);
      prefetchDNS(url.hostname);
      preconnect(url.origin);
    }
    
    // Cleanup memory monitor on app unmount
    return () => {
      memoryMonitor.stop();
    };
  }, []);

  return (
    <ErrorBoundary>
      <ParallelInitProvider queryClient={queryClient}>
        <DuckDBProvider>
          <RustWebSocketProvider>
            <TooltipProvider>
              <Toaster />
              <Sonner />
              <BrowserRouter>
                <Routes>
                  <Route path="/" element={
                    <Suspense fallback={<PageLoader />}>
                      <Index />
                    </Suspense>
                  } />
                  {/* ADD ALL CUSTOM ROUTES ABOVE THE CATCH-ALL "*" ROUTE */}
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </BrowserRouter>
            </TooltipProvider>
          </RustWebSocketProvider>
        </DuckDBProvider>
      </ParallelInitProvider>
    </ErrorBoundary>
  );
};

export default App;
