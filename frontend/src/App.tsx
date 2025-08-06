import React from 'react';
import { prefetchDNS, preconnect } from 'react-dom';
import { Toaster } from "@/components/ui/toaster";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { GraphConfigProvider } from "@/contexts/GraphConfigProvider";
import { WebSocketProvider } from "@/contexts/WebSocketProvider";
import { DuckDBProvider } from "@/contexts/DuckDBProvider";
import ErrorBoundary from "./components/ErrorBoundary";
import Index from "./pages/Index";
import NotFound from "./pages/NotFound";
import { memoryMonitor } from "@/utils/memoryMonitor";
import { clearAllCaches } from "@/utils/clearAllCaches";

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
    // Preconnect to API endpoints if configured
    const apiUrl = import.meta.env.VITE_API_URL;
    if (apiUrl) {
      const url = new URL(apiUrl);
      prefetchDNS(url.hostname);
      preconnect(url.origin);
    }
    
    // Note: Font preloading removed - font files not present in public directory
    // If adding custom fonts, ensure they exist in public/fonts/ first
    
    // Cleanup memory monitor on app unmount
    return () => {
      memoryMonitor.stop();
    };
  }, []);

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <GraphConfigProvider>
          <WebSocketProvider>
            <DuckDBProvider>
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
            </DuckDBProvider>
          </WebSocketProvider>
        </GraphConfigProvider>
      </QueryClientProvider>
    </ErrorBoundary>
  );
};

export default App;
