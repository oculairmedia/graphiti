import React, { useState, useCallback, useEffect, useRef } from 'react';
import { GraphNode } from '../../../api/types';
import { logger } from '../../../utils/logger';

interface PopupPosition {
  x: number;
  y: number;
}

interface PopupContent {
  title?: string;
  body?: React.ReactNode;
  footer?: React.ReactNode;
}

interface PopupConfig {
  position: PopupPosition;
  content: PopupContent;
  nodeId?: string;
  type: 'hover' | 'click' | 'context' | 'custom';
  showArrow?: boolean;
  placement?: 'top' | 'bottom' | 'left' | 'right' | 'auto';
  offset?: { x: number; y: number };
  className?: string;
}

interface PopupManagerProps {
  onPopupShow?: (popup: PopupConfig) => void;
  onPopupHide?: (nodeId?: string) => void;
  showDelay?: number;
  hideDelay?: number;
  maxPopups?: number;
  followMouse?: boolean;
  autoHide?: boolean;
  autoHideDelay?: number;
}

/**
 * PopupManager - Manages node tooltips and popup displays
 * 
 * Features:
 * - Multiple popup types (hover, click, context menu)
 * - Smart positioning to stay in viewport
 * - Delayed show/hide
 * - Follow mouse option
 * - Auto-hide functionality
 */
export const PopupManager: React.FC<PopupManagerProps> = ({
  onPopupShow,
  onPopupHide,
  showDelay = 500,
  hideDelay = 200,
  maxPopups = 1,
  followMouse = false,
  autoHide = true,
  autoHideDelay = 5000
}) => {
  const [activePopups, setActivePopups] = useState<Map<string, PopupConfig>>(new Map());
  const showTimersRef = useRef<Map<string, NodeJS.Timeout>>(new Map());
  const hideTimersRef = useRef<Map<string, NodeJS.Timeout>>(new Map());
  const autoHideTimersRef = useRef<Map<string, NodeJS.Timeout>>(new Map());
  const mousePositionRef = useRef<PopupPosition>({ x: 0, y: 0 });

  // Update mouse position
  useEffect(() => {
    if (!followMouse) return;

    const handleMouseMove = (e: MouseEvent) => {
      mousePositionRef.current = { x: e.clientX, y: e.clientY };
      
      // Update popup positions if following mouse
      setActivePopups(prev => {
        const updated = new Map(prev);
        updated.forEach((popup, key) => {
          if (popup.type === 'hover') {
            updated.set(key, {
              ...popup,
              position: { ...mousePositionRef.current }
            });
          }
        });
        return updated;
      });
    };

    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, [followMouse]);

  // Calculate smart position to keep popup in viewport
  const calculateSmartPosition = useCallback((
    basePosition: PopupPosition,
    placement: string,
    offset: { x: number; y: number } = { x: 0, y: 0 }
  ): PopupPosition => {
    const viewport = {
      width: window.innerWidth,
      height: window.innerHeight
    };

    // Estimated popup size (would be better with actual measurements)
    const popupSize = { width: 200, height: 100 };
    
    let position = { ...basePosition };

    // Apply offset
    position.x += offset.x;
    position.y += offset.y;

    // Adjust for placement
    switch (placement) {
      case 'top':
        position.y -= popupSize.height;
        break;
      case 'bottom':
        position.y += 20;
        break;
      case 'left':
        position.x -= popupSize.width;
        break;
      case 'right':
        position.x += 20;
        break;
    }

    // Keep in viewport
    if (position.x + popupSize.width > viewport.width) {
      position.x = viewport.width - popupSize.width - 10;
    }
    if (position.x < 10) {
      position.x = 10;
    }
    if (position.y + popupSize.height > viewport.height) {
      position.y = viewport.height - popupSize.height - 10;
    }
    if (position.y < 10) {
      position.y = 10;
    }

    return position;
  }, []);

  // Show popup
  const showPopup = useCallback((config: PopupConfig) => {
    const popupId = config.nodeId || `popup-${Date.now()}`;

    // Clear any hide timer for this popup
    const hideTimer = hideTimersRef.current.get(popupId);
    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimersRef.current.delete(popupId);
    }

    // Schedule show with delay
    const showTimer = setTimeout(() => {
      setActivePopups(prev => {
        const newPopups = new Map(prev);
        
        // Enforce max popups limit
        if (newPopups.size >= maxPopups && !newPopups.has(popupId)) {
          // Remove oldest popup
          const firstKey = newPopups.keys().next().value;
          if (firstKey) {
            newPopups.delete(firstKey);
            onPopupHide?.(firstKey);
          }
        }

        // Calculate smart position
        const smartPosition = calculateSmartPosition(
          config.position,
          config.placement || 'auto',
          config.offset
        );

        const finalConfig = {
          ...config,
          position: smartPosition
        };

        newPopups.set(popupId, finalConfig);
        onPopupShow?.(finalConfig);

        // Set auto-hide timer
        if (autoHide && config.type !== 'click') {
          const autoHideTimer = setTimeout(() => {
            hidePopup(popupId);
          }, autoHideDelay);
          autoHideTimersRef.current.set(popupId, autoHideTimer);
        }

        logger.debug('PopupManager: Showing popup', { id: popupId, type: config.type });
        return newPopups;
      });
    }, config.type === 'hover' ? showDelay : 0);

    showTimersRef.current.set(popupId, showTimer);
  }, [maxPopups, showDelay, autoHide, autoHideDelay, calculateSmartPosition, onPopupShow, onPopupHide]);

  // Hide popup
  const hidePopup = useCallback((popupId: string) => {
    // Clear show timer if exists
    const showTimer = showTimersRef.current.get(popupId);
    if (showTimer) {
      clearTimeout(showTimer);
      showTimersRef.current.delete(popupId);
    }

    // Clear auto-hide timer
    const autoHideTimer = autoHideTimersRef.current.get(popupId);
    if (autoHideTimer) {
      clearTimeout(autoHideTimer);
      autoHideTimersRef.current.delete(popupId);
    }

    // Schedule hide with delay
    const hideTimer = setTimeout(() => {
      setActivePopups(prev => {
        const newPopups = new Map(prev);
        if (newPopups.delete(popupId)) {
          onPopupHide?.(popupId);
          logger.debug('PopupManager: Hiding popup', { id: popupId });
        }
        return newPopups;
      });
    }, hideDelay);

    hideTimersRef.current.set(popupId, hideTimer);
  }, [hideDelay, onPopupHide]);

  // Hide all popups
  const hideAllPopups = useCallback(() => {
    // Clear all timers
    showTimersRef.current.forEach(timer => clearTimeout(timer));
    hideTimersRef.current.forEach(timer => clearTimeout(timer));
    autoHideTimersRef.current.forEach(timer => clearTimeout(timer));
    
    showTimersRef.current.clear();
    hideTimersRef.current.clear();
    autoHideTimersRef.current.clear();

    setActivePopups(prev => {
      prev.forEach((_, id) => onPopupHide?.(id));
      return new Map();
    });

    logger.debug('PopupManager: Hidden all popups');
  }, [onPopupHide]);

  // Show node hover popup
  const showNodeHover = useCallback((node: GraphNode, position: PopupPosition) => {
    const config: PopupConfig = {
      position,
      content: {
        title: node.label || node.id,
        body: (
          <div>
            <p>Type: {node.node_type}</p>
            <p>ID: {node.id}</p>
            {node.summary && <p>Summary: {node.summary}</p>}
          </div>
        )
      },
      nodeId: node.id,
      type: 'hover',
      placement: 'top',
      showArrow: true
    };

    showPopup(config);
  }, [showPopup]);

  // Show node click popup
  const showNodeClick = useCallback((node: GraphNode, position: PopupPosition) => {
    const config: PopupConfig = {
      position,
      content: {
        title: node.label || node.id,
        body: (
          <div>
            <p><strong>Details</strong></p>
            <p>Type: {node.node_type}</p>
            <p>Created: {new Date(node.created_at).toLocaleString()}</p>
            <p>Updated: {new Date(node.updated_at).toLocaleString()}</p>
            {node.properties && (
              <details>
                <summary>Properties</summary>
                <pre>{JSON.stringify(node.properties, null, 2)}</pre>
              </details>
            )}
          </div>
        )
      },
      nodeId: node.id,
      type: 'click',
      placement: 'auto',
      showArrow: true
    };

    showPopup(config);
  }, [showPopup]);

  // Show context menu
  const showContextMenu = useCallback((nodeId: string, position: PopupPosition, items: Array<{ label: string; action: () => void }>) => {
    const config: PopupConfig = {
      position,
      content: {
        body: (
          <ul className="context-menu">
            {items.map((item, index) => (
              <li key={index} onClick={item.action}>
                {item.label}
              </li>
            ))}
          </ul>
        )
      },
      nodeId,
      type: 'context',
      placement: 'auto',
      className: 'context-menu-popup'
    };

    showPopup(config);
  }, [showPopup]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      showTimersRef.current.forEach(timer => clearTimeout(timer));
      hideTimersRef.current.forEach(timer => clearTimeout(timer));
      autoHideTimersRef.current.forEach(timer => clearTimeout(timer));
      logger.debug('PopupManager: Cleanup on unmount');
    };
  }, []);

  return null; // This is a non-visual component
};

// Hook for popup management
export const usePopup = () => {
  const [isVisible, setIsVisible] = useState(false);
  const [position, setPosition] = useState<PopupPosition>({ x: 0, y: 0 });
  const [content, setContent] = useState<PopupContent>({});

  const show = useCallback((pos: PopupPosition, cont: PopupContent) => {
    setPosition(pos);
    setContent(cont);
    setIsVisible(true);
  }, []);

  const hide = useCallback(() => {
    setIsVisible(false);
  }, []);

  const update = useCallback((pos?: PopupPosition, cont?: PopupContent) => {
    if (pos) setPosition(pos);
    if (cont) setContent(cont);
  }, []);

  return {
    isVisible,
    position,
    content,
    show,
    hide,
    update
  };
};

export default PopupManager;