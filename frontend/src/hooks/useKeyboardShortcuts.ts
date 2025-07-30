import { useEffect, useCallback } from 'react';
import { useGraphConfig } from '@/contexts/GraphConfigProvider';

interface KeyboardShortcutsProps {
  onSelectAll?: () => void;
  onDeselectAll?: () => void;
  cosmographRef?: React.MutableRefObject<any>;
}

export const useKeyboardShortcuts = ({ 
  onSelectAll,
  onDeselectAll,
  cosmographRef
}: KeyboardShortcutsProps) => {
  const { config, updateConfig, zoomIn, zoomOut, fitView } = useGraphConfig();

  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    // Only process if shortcuts are enabled
    if (!config.enableKeyboardShortcuts) return;

    // Don't interfere with input fields
    const target = event.target as HTMLElement;
    if (target && (
        target instanceof HTMLInputElement || 
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement)) {
      return;
    }

    const key = event.key.toLowerCase();
    const isCtrlOrCmd = event.ctrlKey || event.metaKey;

    switch (key) {
      // Fit view
      case 'f':
        if (!isCtrlOrCmd) {
          event.preventDefault();
          fitView();
        }
        break;

      // Zoom in
      case '+':
      case '=':
        event.preventDefault();
        zoomIn();
        break;

      // Zoom out
      case '-':
      case '_':
        event.preventDefault();
        zoomOut();
        break;

      // Pan with arrow keys
      case 'arrowup':
        event.preventDefault();
        if (cosmographRef?.current?._camera) {
          // Access the camera and pan it
          const camera = cosmographRef.current._camera;
          camera.pan({ x: 0, y: -50 });
        }
        break;
      case 'arrowdown':
        event.preventDefault();
        if (cosmographRef?.current?._camera) {
          const camera = cosmographRef.current._camera;
          camera.pan({ x: 0, y: 50 });
        }
        break;
      case 'arrowleft':
        event.preventDefault();
        if (cosmographRef?.current?._camera) {
          const camera = cosmographRef.current._camera;
          camera.pan({ x: -50, y: 0 });
        }
        break;
      case 'arrowright':
        event.preventDefault();
        if (cosmographRef?.current?._camera) {
          const camera = cosmographRef.current._camera;
          camera.pan({ x: 50, y: 0 });
        }
        break;

      // Select all (Ctrl/Cmd + A)
      case 'a':
        if (isCtrlOrCmd) {
          event.preventDefault();
          onSelectAll?.();
        }
        break;

      // Deselect all (Escape)
      case 'escape':
        event.preventDefault();
        onDeselectAll?.();
        break;

      // Toggle physics (Space)
      case ' ':
        event.preventDefault();
        updateConfig({ 
          disableSimulation: config.disableSimulation ? null : true 
        });
        break;

      // Toggle labels (L)
      case 'l':
        if (!isCtrlOrCmd) {
          event.preventDefault();
          updateConfig({ renderLabels: !config.renderLabels });
        }
        break;

      // Reset zoom (R)
      case 'r':
        if (!isCtrlOrCmd) {
          event.preventDefault();
          fitView();
        }
        break;

      // Toggle debug info (D)
      case 'd':
        if (!isCtrlOrCmd) {
          event.preventDefault();
          updateConfig({ showDebugInfo: !config.showDebugInfo });
        }
        break;

      // Focus search (Ctrl/Cmd + F)
      case 'f':
        if (isCtrlOrCmd) {
          event.preventDefault();
          // Change to search mode and focus search input
          updateConfig({ queryType: 'search' });
          
          // Focus the search input after a small delay to allow UI update
          setTimeout(() => {
            const searchInput = document.querySelector('input[placeholder="Enter search term..."]') as HTMLInputElement;
            if (searchInput) {
              searchInput.focus();
              searchInput.select();
            }
          }, 100);
        }
        break;
      
      // Number keys for quick layout switching
      case '1':
        if (!isCtrlOrCmd) {
          event.preventDefault();
          updateConfig({ layout: 'force-directed' });
        }
        break;
      case '2':
        if (!isCtrlOrCmd) {
          event.preventDefault();
          updateConfig({ layout: 'hierarchical' });
        }
        break;
      case '3':
        if (!isCtrlOrCmd) {
          event.preventDefault();
          updateConfig({ layout: 'radial' });
        }
        break;
      case '4':
        if (!isCtrlOrCmd) {
          event.preventDefault();
          updateConfig({ layout: 'circular' });
        }
        break;
      case '5':
        if (!isCtrlOrCmd) {
          event.preventDefault();
          updateConfig({ layout: 'temporal' });
        }
        break;
      case '6':
        if (!isCtrlOrCmd) {
          event.preventDefault();
          updateConfig({ layout: 'cluster' });
        }
        break;
    }
  }, [config.enableKeyboardShortcuts, config.disableSimulation, config.renderLabels, 
      config.showDebugInfo, updateConfig, onSelectAll, onDeselectAll, zoomIn, zoomOut, fitView, cosmographRef]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [handleKeyDown]);

  return {
    // Export any functions if needed
  };
};