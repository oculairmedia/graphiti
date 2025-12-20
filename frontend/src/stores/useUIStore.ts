import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface UIState {
  // Panel visibility
  leftPanelCollapsed: boolean;
  showFilterPanel: boolean;
  showStatsPanel: boolean;
  showMonitoringPanel: boolean;
  isTimelineVisible: boolean;
  
  // Fullscreen
  isFullscreen: boolean;
  
  // Timeline settings
  timelineUpdateMode: 'instant' | 'animated';
  
  // Actions
  setLeftPanelCollapsed: (collapsed: boolean) => void;
  toggleLeftPanel: () => void;
  setShowFilterPanel: (show: boolean) => void;
  toggleFilterPanel: () => void;
  setShowStatsPanel: (show: boolean) => void;
  toggleStatsPanel: () => void;
  setShowMonitoringPanel: (show: boolean) => void;
  toggleMonitoringPanel: () => void;
  setIsTimelineVisible: (visible: boolean) => void;
  toggleTimeline: () => void;
  setIsFullscreen: (fullscreen: boolean) => void;
  toggleFullscreen: () => void;
  setTimelineUpdateMode: (mode: 'instant' | 'animated') => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      // Initial state
      leftPanelCollapsed: false,
      showFilterPanel: false,
      showStatsPanel: false,
      showMonitoringPanel: false,
      isTimelineVisible: true,
      isFullscreen: false,
      timelineUpdateMode: 'animated',
      
      // Actions
      setLeftPanelCollapsed: (collapsed) => set({ leftPanelCollapsed: collapsed }),
      toggleLeftPanel: () => set((state) => ({ leftPanelCollapsed: !state.leftPanelCollapsed })),
      
      setShowFilterPanel: (show) => set({ showFilterPanel: show }),
      toggleFilterPanel: () => set((state) => ({ showFilterPanel: !state.showFilterPanel })),
      
      setShowStatsPanel: (show) => set({ showStatsPanel: show }),
      toggleStatsPanel: () => set((state) => ({ showStatsPanel: !state.showStatsPanel })),
      
      setShowMonitoringPanel: (show) => set({ showMonitoringPanel: show }),
      toggleMonitoringPanel: () => set((state) => ({ showMonitoringPanel: !state.showMonitoringPanel })),
      
      setIsTimelineVisible: (visible) => set({ isTimelineVisible: visible }),
      toggleTimeline: () => set((state) => ({ isTimelineVisible: !state.isTimelineVisible })),
      
      setIsFullscreen: (fullscreen) => set({ isFullscreen: fullscreen }),
      toggleFullscreen: () => set((state) => ({ isFullscreen: !state.isFullscreen })),
      
      setTimelineUpdateMode: (mode) => set({ timelineUpdateMode: mode }),
    }),
    {
      name: 'graphiti-ui-storage',
      partialize: (state) => ({
        // Only persist these fields
        leftPanelCollapsed: state.leftPanelCollapsed,
        isTimelineVisible: state.isTimelineVisible,
        timelineUpdateMode: state.timelineUpdateMode,
      }),
    }
  )
);
