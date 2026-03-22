import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';

interface LiveStats {
  nodeCount: number;
  edgeCount: number;
  lastUpdated: number;
}

interface StreamingProgress {
  loaded: number;
  total: number;
  phase: 'nodes' | 'edges' | '';
  isStreaming: boolean;
}

interface GraphState {
  // Simulation state
  isSimulationRunning: boolean;
  isContextReady: boolean;
  
  // Live statistics
  liveStats: LiveStats | null;
  
  // Loading states
  isLoading: boolean;
  isRefreshing: boolean;
  error: string | null;
  
  // Streaming progress for initial data load
  streamingProgress: StreamingProgress;
  
  // Actions
  setSimulationRunning: (running: boolean) => void;
  toggleSimulation: () => void;
  setContextReady: (ready: boolean) => void;
  
  setLiveStats: (stats: LiveStats | null) => void;
  updateLiveStats: (partial: Partial<LiveStats>) => void;
  
  setLoading: (loading: boolean) => void;
  setRefreshing: (refreshing: boolean) => void;
  setError: (error: string | null) => void;
  clearError: () => void;
  
  setStreamingProgress: (loaded: number, total: number, phase: 'nodes' | 'edges') => void;
  clearStreamingProgress: () => void;
}

export const useGraphStore = create<GraphState>()(
  subscribeWithSelector((set, get) => ({
    // Initial state
    isSimulationRunning: true,
    isContextReady: false,
    liveStats: null,
    isLoading: false,
    isRefreshing: false,
    error: null,
    streamingProgress: { loaded: 0, total: 0, phase: '', isStreaming: false },
    
    // Simulation actions
    setSimulationRunning: (running) => set({ isSimulationRunning: running }),
    toggleSimulation: () => set((state) => ({ isSimulationRunning: !state.isSimulationRunning })),
    setContextReady: (ready) => set({ isContextReady: ready }),
    
    // Stats actions
    setLiveStats: (stats) => set({ liveStats: stats }),
    updateLiveStats: (partial) => set((state) => ({
      liveStats: state.liveStats 
        ? { ...state.liveStats, ...partial, lastUpdated: Date.now() }
        : { nodeCount: 0, edgeCount: 0, lastUpdated: Date.now(), ...partial }
    })),
    
    // Loading actions
    setLoading: (loading) => set({ isLoading: loading }),
    setRefreshing: (refreshing) => set({ isRefreshing: refreshing }),
    setError: (error) => set({ error }),
    clearError: () => set({ error: null }),
    
    setStreamingProgress: (loaded, total, phase) => set({
      streamingProgress: { loaded, total, phase, isStreaming: true }
    }),
    clearStreamingProgress: () => set({
      streamingProgress: { loaded: 0, total: 0, phase: '', isStreaming: false }
    }),
  }))
);

// Selector helpers
export const selectIsSimulationRunning = (state: GraphState) => state.isSimulationRunning;
export const selectLiveStats = (state: GraphState) => state.liveStats;
export const selectIsLoading = (state: GraphState) => state.isLoading;
