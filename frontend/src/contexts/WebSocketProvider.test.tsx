import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act, renderHook } from '../test/utils';
import { WebSocketProvider, useWebSocketContext } from './WebSocketProvider';
import React from 'react';

describe('WebSocketProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Provider Initialization', () => {
    it('should render children correctly', () => {
      render(
        <WebSocketProvider>
          <div>Test Child</div>
        </WebSocketProvider>
      );
      
      expect(screen.getByText('Test Child')).toBeInTheDocument();
    });
  });

  describe('useWebSocketContext Hook', () => {
    it('should provide WebSocket context values', () => {
      const { result } = renderHook(() => useWebSocketContext(), {
        wrapper: ({ children }) => <WebSocketProvider>{children}</WebSocketProvider>,
      });

      expect(result.current).toHaveProperty('isConnected');
      expect(result.current).toHaveProperty('connectionQuality');
      expect(result.current).toHaveProperty('latency');
      expect(result.current).toHaveProperty('subscribe');
      expect(result.current).toHaveProperty('subscribeToNodeAccess');
    });

    it('should start with disconnected status', () => {
      const { result } = renderHook(() => useWebSocketContext(), {
        wrapper: ({ children }) => <WebSocketProvider>{children}</WebSocketProvider>,
      });

      expect(result.current.isConnected).toBe(false);
    });

    it('should provide subscription methods', () => {
      const { result } = renderHook(() => useWebSocketContext(), {
        wrapper: ({ children }) => <WebSocketProvider>{children}</WebSocketProvider>,
      });

      expect(typeof result.current.subscribe).toBe('function');
      expect(typeof result.current.subscribeToNodeAccess).toBe('function');
      expect(typeof result.current.subscribeToGraphUpdate).toBe('function');
      expect(typeof result.current.subscribeToDeltaUpdate).toBe('function');
      expect(typeof result.current.subscribeToCacheInvalidate).toBe('function');
    });
  });

  describe('Message Handling', () => {
    it('should handle graph update events', () => {
      const { result } = renderHook(() => useWebSocketContext(), {
        wrapper: ({ children }) => <WebSocketProvider>{children}</WebSocketProvider>,
      });

      // Setup subscription
      const handler = vi.fn();
      const unsubscribe = result.current.subscribeToGraphUpdate(handler);

      // Check that we can unsubscribe
      expect(typeof unsubscribe).toBe('function');
      
      // lastGraphUpdateEvent should be defined (can be null initially)
      expect(result.current).toHaveProperty('lastGraphUpdateEvent');
    });

    it('should provide update stats', () => {
      const { result } = renderHook(() => useWebSocketContext(), {
        wrapper: ({ children }) => <WebSocketProvider>{children}</WebSocketProvider>,
      });

      expect(result.current.updateStats).toBeDefined();
      expect(result.current.updateStats).toHaveProperty('totalUpdates');
      expect(result.current.updateStats).toHaveProperty('deltaUpdates');
      expect(result.current.updateStats).toHaveProperty('cacheInvalidations');
      expect(result.current.updateStats).toHaveProperty('lastUpdateTime');
    });
  });

  describe('Connection Management', () => {
    it('should provide connection quality', () => {
      const { result } = renderHook(() => useWebSocketContext(), {
        wrapper: ({ children }) => <WebSocketProvider>{children}</WebSocketProvider>,
      });

      expect(result.current.connectionQuality).toBeDefined();
      expect(['excellent', 'good', 'poor']).toContain(result.current.connectionQuality);
    });

    it('should provide latency information', () => {
      const { result } = renderHook(() => useWebSocketContext(), {
        wrapper: ({ children }) => <WebSocketProvider>{children}</WebSocketProvider>,
      });

      expect(result.current.latency).toBeDefined();
      expect(typeof result.current.latency).toBe('number');
    });
  });

  describe('Event Properties', () => {
    it('should provide last event properties', () => {
      const { result } = renderHook(() => useWebSocketContext(), {
        wrapper: ({ children }) => <WebSocketProvider>{children}</WebSocketProvider>,
      });

      expect(result.current).toHaveProperty('lastNodeAccessEvent');
      expect(result.current).toHaveProperty('lastGraphUpdateEvent');
      expect(result.current).toHaveProperty('lastDeltaUpdateEvent');
    });
  });
});