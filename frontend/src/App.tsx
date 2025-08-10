import React from 'react';
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
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import { memoryMonitor } from "@/utils/memoryMonitor";
import { preloader } from "@/services/preloader";
import { preloadDuckDB } from "@/services/duckdb-lazy-loader";

// Create query client once
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // Consider data fresh for 5 minutes
      cacheTime: 10 * 60 * 1000, // Keep in cache for 10 minutes
      refetchOnWindowFocus: false, // Don't refetch on window focus
      refetchOnReconnect: false, // Don't refetch on reconnect
      retry: 1, // Retry failed requests only once
      retryDelay: 1000, // 1 second retry delay
    },
  },
});

const App = () => {
  // Preload resources for better performance
  React.useEffect(() => {
    // Start preloading if not already started
    if (!preloader.isPreloaded('nodes')) {
      console.log('[App] Starting data preload...');
      preloader.startPreloading();
    }
    
    // Start preloading DuckDB in the background
    preloadDuckDB();
    
    // Preconnect to API endpoints if configured
    const apiUrl = import.meta.env.VITE_API_URL;
    if (apiUrl) {
      const url = new URL(apiUrl);
      prefetchDNS(url.hostname);
      preconnect(url.origin);
    }
    
    // Log preloader stats
    const stats = preloader.getStats();
    console.log('[App] Preloader stats:', stats);
    
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
                  <Route path="/" element={<Index />} />
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
