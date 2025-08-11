import React, { useEffect, useCallback, useState, useMemo } from 'react';

interface Shortcut {
  id: string;
  key: string;
  modifiers?: Array<'ctrl' | 'alt' | 'shift' | 'meta'>;
  description: string;
  category: string;
  action: () => void;
  enabled?: boolean;
  preventDefault?: boolean;
}

interface ShortcutCategory {
  name: string;
  shortcuts: Shortcut[];
}

interface KeyboardShortcutsProps {
  shortcuts?: Shortcut[];
  onShortcutTriggered?: (shortcut: Shortcut) => void;
  enabled?: boolean;
  children?: React.ReactNode;
}

interface KeyboardState {
  pressedKeys: Set<string>;
  lastShortcut: Shortcut | null;
  isRecording: boolean;
  recordedKeys: string[];
}

/**
 * KeyboardShortcuts - Comprehensive keyboard shortcut management
 * Provides customizable shortcuts for graph navigation and manipulation
 */
export const KeyboardShortcuts: React.FC<KeyboardShortcutsProps> = React.memo(({
  shortcuts = getDefaultShortcuts(),
  onShortcutTriggered,
  enabled = true,
  children
}) => {
  const [state, setState] = useState<KeyboardState>({
    pressedKeys: new Set(),
    lastShortcut: null,
    isRecording: false,
    recordedKeys: []
  });

  const [customShortcuts, setCustomShortcuts] = useState<Map<string, Shortcut>>(new Map());

  // Get default shortcuts
  function getDefaultShortcuts(): Shortcut[] {
    return [
      // Navigation
      {
        id: 'pan-up',
        key: 'ArrowUp',
        description: 'Pan up',
        category: 'Navigation',
        action: () => console.log('Pan up'),
        enabled: true
      },
      {
        id: 'pan-down',
        key: 'ArrowDown',
        description: 'Pan down',
        category: 'Navigation',
        action: () => console.log('Pan down'),
        enabled: true
      },
      {
        id: 'pan-left',
        key: 'ArrowLeft',
        description: 'Pan left',
        category: 'Navigation',
        action: () => console.log('Pan left'),
        enabled: true
      },
      {
        id: 'pan-right',
        key: 'ArrowRight',
        description: 'Pan right',
        category: 'Navigation',
        action: () => console.log('Pan right'),
        enabled: true
      },
      {
        id: 'zoom-in',
        key: '=',
        modifiers: ['ctrl'],
        description: 'Zoom in',
        category: 'Navigation',
        action: () => console.log('Zoom in'),
        enabled: true,
        preventDefault: true
      },
      {
        id: 'zoom-out',
        key: '-',
        modifiers: ['ctrl'],
        description: 'Zoom out',
        category: 'Navigation',
        action: () => console.log('Zoom out'),
        enabled: true,
        preventDefault: true
      },
      {
        id: 'fit-view',
        key: 'f',
        description: 'Fit view to content',
        category: 'Navigation',
        action: () => console.log('Fit view'),
        enabled: true
      },
      {
        id: 'center-view',
        key: 'c',
        description: 'Center view',
        category: 'Navigation',
        action: () => console.log('Center view'),
        enabled: true
      },

      // Selection
      {
        id: 'select-all',
        key: 'a',
        modifiers: ['ctrl'],
        description: 'Select all nodes',
        category: 'Selection',
        action: () => console.log('Select all'),
        enabled: true,
        preventDefault: true
      },
      {
        id: 'deselect-all',
        key: 'd',
        modifiers: ['ctrl'],
        description: 'Deselect all',
        category: 'Selection',
        action: () => console.log('Deselect all'),
        enabled: true,
        preventDefault: true
      },
      {
        id: 'invert-selection',
        key: 'i',
        modifiers: ['ctrl'],
        description: 'Invert selection',
        category: 'Selection',
        action: () => console.log('Invert selection'),
        enabled: true,
        preventDefault: true
      },
      {
        id: 'select-connected',
        key: 'e',
        modifiers: ['shift'],
        description: 'Select connected nodes',
        category: 'Selection',
        action: () => console.log('Select connected'),
        enabled: true
      },
      {
        id: 'selection-mode-rect',
        key: 'r',
        description: 'Rectangle selection mode',
        category: 'Selection',
        action: () => console.log('Rect mode'),
        enabled: true
      },
      {
        id: 'selection-mode-lasso',
        key: 'l',
        description: 'Lasso selection mode',
        category: 'Selection',
        action: () => console.log('Lasso mode'),
        enabled: true
      },

      // Search
      {
        id: 'search',
        key: '/',
        description: 'Open search',
        category: 'Search',
        action: () => console.log('Open search'),
        enabled: true,
        preventDefault: true
      },
      {
        id: 'search-next',
        key: 'n',
        description: 'Next search result',
        category: 'Search',
        action: () => console.log('Next result'),
        enabled: true
      },
      {
        id: 'search-previous',
        key: 'p',
        modifiers: ['shift'],
        description: 'Previous search result',
        category: 'Search',
        action: () => console.log('Previous result'),
        enabled: true
      },
      {
        id: 'clear-search',
        key: 'Escape',
        description: 'Clear search',
        category: 'Search',
        action: () => console.log('Clear search'),
        enabled: true
      },

      // Visualization
      {
        id: 'toggle-labels',
        key: 't',
        description: 'Toggle labels',
        category: 'Visualization',
        action: () => console.log('Toggle labels'),
        enabled: true
      },
      {
        id: 'toggle-edges',
        key: 'e',
        description: 'Toggle edges',
        category: 'Visualization',
        action: () => console.log('Toggle edges'),
        enabled: true
      },
      {
        id: 'cycle-color-scheme',
        key: 'c',
        modifiers: ['shift'],
        description: 'Cycle color scheme',
        category: 'Visualization',
        action: () => console.log('Cycle colors'),
        enabled: true
      },
      {
        id: 'cycle-layout',
        key: 'l',
        modifiers: ['shift'],
        description: 'Cycle layout algorithm',
        category: 'Visualization',
        action: () => console.log('Cycle layout'),
        enabled: true
      },

      // Data
      {
        id: 'refresh',
        key: 'r',
        modifiers: ['ctrl'],
        description: 'Refresh data',
        category: 'Data',
        action: () => console.log('Refresh'),
        enabled: true,
        preventDefault: true
      },
      {
        id: 'export',
        key: 's',
        modifiers: ['ctrl'],
        description: 'Export graph',
        category: 'Data',
        action: () => console.log('Export'),
        enabled: true,
        preventDefault: true
      },
      {
        id: 'undo',
        key: 'z',
        modifiers: ['ctrl'],
        description: 'Undo',
        category: 'Data',
        action: () => console.log('Undo'),
        enabled: true,
        preventDefault: true
      },
      {
        id: 'redo',
        key: 'y',
        modifiers: ['ctrl'],
        description: 'Redo',
        category: 'Data',
        action: () => console.log('Redo'),
        enabled: true,
        preventDefault: true
      },

      // Help
      {
        id: 'help',
        key: '?',
        modifiers: ['shift'],
        description: 'Show help',
        category: 'Help',
        action: () => console.log('Show help'),
        enabled: true
      },
      {
        id: 'shortcuts-overlay',
        key: 'k',
        modifiers: ['ctrl'],
        description: 'Show shortcuts overlay',
        category: 'Help',
        action: () => console.log('Show shortcuts'),
        enabled: true,
        preventDefault: true
      }
    ];
  }

  // Merge default and custom shortcuts
  const allShortcuts = useMemo(() => {
    const merged = new Map<string, Shortcut>();
    
    // Add default shortcuts
    shortcuts.forEach(shortcut => {
      const key = generateShortcutKey(shortcut);
      merged.set(key, shortcut);
    });
    
    // Override with custom shortcuts
    customShortcuts.forEach((shortcut, key) => {
      merged.set(key, shortcut);
    });
    
    return Array.from(merged.values());
  }, [shortcuts, customShortcuts]);

  // Generate unique key for shortcut
  function generateShortcutKey(shortcut: Shortcut): string {
    const modifiers = shortcut.modifiers || [];
    const parts = [...modifiers.sort(), shortcut.key];
    return parts.join('+');
  }

  // Check if shortcut matches current key state
  function isShortcutMatch(shortcut: Shortcut, event: KeyboardEvent): boolean {
    if (!shortcut.enabled) return false;
    
    // Check main key
    if (event.key !== shortcut.key && event.code !== shortcut.key) {
      return false;
    }
    
    // Check modifiers
    const modifiers = shortcut.modifiers || [];
    const hasCtrl = modifiers.includes('ctrl');
    const hasAlt = modifiers.includes('alt');
    const hasShift = modifiers.includes('shift');
    const hasMeta = modifiers.includes('meta');
    
    return event.ctrlKey === hasCtrl &&
           event.altKey === hasAlt &&
           event.shiftKey === hasShift &&
           event.metaKey === hasMeta;
  }

  // Handle key down
  const handleKeyDown = useCallback((event: KeyboardEvent) => {
    if (!enabled) return;
    
    // Don't handle shortcuts when typing in input fields
    const target = event.target as HTMLElement;
    if (target.tagName === 'INPUT' || 
        target.tagName === 'TEXTAREA' || 
        target.contentEditable === 'true') {
      return;
    }
    
    // Record key if in recording mode
    if (state.isRecording) {
      setState(prev => ({
        ...prev,
        recordedKeys: [...prev.recordedKeys, event.key],
        pressedKeys: new Set([...prev.pressedKeys, event.key])
      }));
      event.preventDefault();
      return;
    }
    
    // Add to pressed keys
    setState(prev => ({
      ...prev,
      pressedKeys: new Set([...prev.pressedKeys, event.key])
    }));
    
    // Check for matching shortcuts
    for (const shortcut of allShortcuts) {
      if (isShortcutMatch(shortcut, event)) {
        // Prevent default if specified
        if (shortcut.preventDefault) {
          event.preventDefault();
        }
        
        // Execute action
        shortcut.action();
        
        // Update state
        setState(prev => ({
          ...prev,
          lastShortcut: shortcut
        }));
        
        // Notify parent
        onShortcutTriggered?.(shortcut);
        
        break;
      }
    }
  }, [enabled, state.isRecording, allShortcuts, onShortcutTriggered]);

  // Handle key up
  const handleKeyUp = useCallback((event: KeyboardEvent) => {
    setState(prev => {
      const pressedKeys = new Set(prev.pressedKeys);
      pressedKeys.delete(event.key);
      return { ...prev, pressedKeys };
    });
  }, []);

  // Start recording shortcut
  const startRecording = useCallback(() => {
    setState(prev => ({
      ...prev,
      isRecording: true,
      recordedKeys: []
    }));
  }, []);

  // Stop recording and return recorded shortcut
  const stopRecording = useCallback((): string => {
    const recorded = state.recordedKeys.join('+');
    setState(prev => ({
      ...prev,
      isRecording: false,
      recordedKeys: []
    }));
    return recorded;
  }, [state.recordedKeys]);

  // Add custom shortcut
  const addCustomShortcut = useCallback((shortcut: Shortcut) => {
    const key = generateShortcutKey(shortcut);
    setCustomShortcuts(prev => new Map(prev).set(key, shortcut));
  }, []);

  // Remove custom shortcut
  const removeCustomShortcut = useCallback((shortcutId: string) => {
    setCustomShortcuts(prev => {
      const updated = new Map(prev);
      updated.forEach((shortcut, key) => {
        if (shortcut.id === shortcutId) {
          updated.delete(key);
        }
      });
      return updated;
    });
  }, []);

  // Reset to default shortcuts
  const resetToDefaults = useCallback(() => {
    setCustomShortcuts(new Map());
  }, []);

  // Get shortcuts by category
  const getShortcutsByCategory = useCallback((): ShortcutCategory[] => {
    const categories = new Map<string, Shortcut[]>();
    
    allShortcuts.forEach(shortcut => {
      if (!categories.has(shortcut.category)) {
        categories.set(shortcut.category, []);
      }
      categories.get(shortcut.category)!.push(shortcut);
    });
    
    return Array.from(categories.entries()).map(([name, shortcuts]) => ({
      name,
      shortcuts
    }));
  }, [allShortcuts]);

  // Format shortcut for display
  const formatShortcut = useCallback((shortcut: Shortcut): string => {
    const parts: string[] = [];
    
    if (shortcut.modifiers) {
      const modifierSymbols: Record<string, string> = {
        'ctrl': '⌃',
        'alt': '⌥',
        'shift': '⇧',
        'meta': '⌘'
      };
      
      shortcut.modifiers.forEach(mod => {
        parts.push(modifierSymbols[mod] || mod);
      });
    }
    
    // Format key
    const keyDisplay = shortcut.key.length === 1 
      ? shortcut.key.toUpperCase()
      : shortcut.key;
    
    parts.push(keyDisplay);
    
    return parts.join(' ');
  }, []);

  // Set up event listeners
  useEffect(() => {
    if (!enabled) return;
    
    window.addEventListener('keydown', handleKeyDown);
    window.addEventListener('keyup', handleKeyUp);
    
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      window.removeEventListener('keyup', handleKeyUp);
    };
  }, [enabled, handleKeyDown, handleKeyUp]);

  // Context value
  const contextValue = useMemo(() => ({
    ...state,
    shortcuts: allShortcuts,
    startRecording,
    stopRecording,
    addCustomShortcut,
    removeCustomShortcut,
    resetToDefaults,
    getShortcutsByCategory,
    formatShortcut,
    isShortcutActive: (shortcutId: string) => state.lastShortcut?.id === shortcutId
  }), [state, allShortcuts, startRecording, stopRecording, addCustomShortcut, 
      removeCustomShortcut, resetToDefaults, getShortcutsByCategory, formatShortcut]);

  return (
    <KeyboardContext.Provider value={contextValue}>
      {children}
    </KeyboardContext.Provider>
  );
}, (prevProps, nextProps) => {
  // Custom comparison to prevent unnecessary re-renders
  // Deep compare shortcuts array if it's not the same reference
  const shortcutsEqual = prevProps.shortcuts === nextProps.shortcuts || 
    (Array.isArray(prevProps.shortcuts) && Array.isArray(nextProps.shortcuts) &&
     prevProps.shortcuts.length === nextProps.shortcuts.length &&
     prevProps.shortcuts.every((s, i) => s.id === nextProps.shortcuts[i].id));
  
  return (
    shortcutsEqual &&
    prevProps.enabled === nextProps.enabled &&
    prevProps.children === nextProps.children &&
    prevProps.onShortcutTriggered === nextProps.onShortcutTriggered
  );
});

// Context
const KeyboardContext = React.createContext<any>({});

export const useKeyboardShortcuts = () => React.useContext(KeyboardContext);