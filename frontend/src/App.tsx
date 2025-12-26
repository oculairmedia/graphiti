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
// v4: Fixed 16-column schema for cosmograph_points table
const SCHEMA_VERSION = 'v4';
const SCHEMA_VERSION_KEY = 'graphiti_cosmograph_schema_version';

// Synchronous IndexedDB cleanup - runs before React renders
(function clearStaleDuckDB() {
  const storedVersion = localStorage.getItem(SCHEMA_VERSION_KEY);
  const needsClear = storedVersion !== SCHEMA_VERSION;
  
  if (needsClear) {
    console.log(`[App] Schema version changed (${storedVersion} -> ${SCHEMA_VERSION}), clearing DuckDB storage...`);
    
    // Clear all potential DuckDB/Cosmograph database names
    // DuckDB-WASM uses various naming patterns for OPFS and IndexedDB
    const dbPatterns = [
      'cosmograph',
      'duckdb',
      'cosmograph_points',
      'cosmograph_links',
      '/cosmograph',
      '/duckdb',
      'duckdb-wasm',
      '/duckdb-wasm',
      'duckdb-wasm-opfs',
      '/duckdb-wasm-opfs',
      'opfs-duckdb',
      '/opfs-duckdb'
    ];
    
    let deletedCount = 0;
    dbPatterns.forEach(name => {
      try {
        const req = indexedDB.deleteDatabase(name);
        req.onsuccess = () => {
          deletedCount++;
          console.log(`[App] Deleted database: ${name}`);
        };
        req.onerror = () => {
          // Ignore errors for non-existent databases
        };
      } catch (e) {
        // Ignore errors
      }
    });
    
    // Also enumerate and delete any matching databases
    if (typeof indexedDB.databases === 'function') {
      indexedDB.databases().then(databases => {
        databases.forEach(db => {
          if (db.name) {
            const name = db.name.toLowerCase();
            const shouldDelete = 
              name.includes('duckdb') || 
              name.includes('cosmograph') || 
              name.includes('opfs') ||
              name.includes('wasm');
            if (shouldDelete) {
              console.log(`[App] Deleting enumerated database: ${db.name}`);
              indexedDB.deleteDatabase(db.name);
              deletedCount++;
            }
          }
        });
      }).catch(() => {});
    }
    
    // Try to clear OPFS storage as well (used by DuckDB-WASM in some browsers)
    if ('storage' in navigator && 'getDirectory' in (navigator.storage as unknown as { getDirectory?: () => Promise<FileSystemDirectoryHandle> })) {
      (navigator.storage as unknown as { getDirectory: () => Promise<FileSystemDirectoryHandle> }).getDirectory().then(async (root: FileSystemDirectoryHandle) => {
        try {
          // Try to delete DuckDB OPFS directory
          await root.removeEntry('duckdb', { recursive: true });
          console.log('[App] Deleted OPFS duckdb directory');
        } catch (e) {
          // Directory might not exist, that's fine
        }
        try {
          await root.removeEntry('.duckdb', { recursive: true });
          console.log('[App] Deleted OPFS .duckdb directory');
        } catch (e) {
          // Directory might not exist
        }
      }).catch(() => {
        // OPFS not available or permission denied
      });
    }
    
    // Update version AFTER initiating deletions
    localStorage.setItem(SCHEMA_VERSION_KEY, SCHEMA_VERSION);
    
    // Force page reload to ensure clean state (only if we had a previous version)
    if (storedVersion !== null) {
      console.log('[App] Reloading page to ensure clean DuckDB state...');
      // Small delay to allow deletion requests to be initiated
      setTimeout(() => {
        window.location.reload();
      }, 100);
    }
  }
})();

const App = () => {
  // Preload resources for better performance
  React.useEffect(() => {
    
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
