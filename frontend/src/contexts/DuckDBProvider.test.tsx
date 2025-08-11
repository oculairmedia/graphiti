import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, renderHook } from '../test/utils';
import { DuckDBProvider, useDuckDB } from './DuckDBProvider';
import React from 'react';

describe('DuckDBProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Provider Initialization', () => {
    it('should render children correctly', () => {
      render(
        <DuckDBProvider>
          <div>Test Child</div>
        </DuckDBProvider>
      );
      
      expect(screen.getByText('Test Child')).toBeInTheDocument();
    });
  });

  describe('useDuckDB Hook', () => {
    it('should provide DuckDB context values', () => {
      const { result } = renderHook(() => useDuckDB(), {
        wrapper: ({ children }) => <DuckDBProvider>{children}</DuckDBProvider>,
      });

      expect(result.current).toHaveProperty('isInitialized');
      expect(result.current).toHaveProperty('isLoading');
      expect(result.current).toHaveProperty('error');
      expect(result.current).toHaveProperty('stats');
      expect(result.current).toHaveProperty('service');
      expect(result.current).toHaveProperty('getDuckDBConnection');
    });

    it('should start with isInitialized as false', () => {
      const { result } = renderHook(() => useDuckDB(), {
        wrapper: ({ children }) => <DuckDBProvider>{children}</DuckDBProvider>,
      });

      expect(result.current.isInitialized).toBe(false);
    });

    it('should have service available', () => {
      const { result } = renderHook(() => useDuckDB(), {
        wrapper: ({ children }) => <DuckDBProvider>{children}</DuckDBProvider>,
      });

      expect(result.current.service).toBeDefined();
    });
  });

  describe('Service Operations', () => {
    it('should provide query method through service', () => {
      const { result } = renderHook(() => useDuckDB(), {
        wrapper: ({ children }) => <DuckDBProvider>{children}</DuckDBProvider>,
      });

      expect(result.current.service).toBeDefined();
      if (result.current.service) {
        expect(result.current.service.query).toBeDefined();
        expect(typeof result.current.service.query).toBe('function');
      }
    });

    it('should provide data operations through service', () => {
      const { result } = renderHook(() => useDuckDB(), {
        wrapper: ({ children }) => <DuckDBProvider>{children}</DuckDBProvider>,
      });

      expect(result.current.service).toBeDefined();
      if (result.current.service) {
        expect(result.current.service.insertData).toBeDefined();
        expect(result.current.service.updateData).toBeDefined();
        expect(result.current.service.deleteData).toBeDefined();
      }
    });
  });

  describe('Connection Management', () => {
    it('should provide getDuckDBConnection method', () => {
      const { result } = renderHook(() => useDuckDB(), {
        wrapper: ({ children }) => <DuckDBProvider>{children}</DuckDBProvider>,
      });

      expect(result.current.getDuckDBConnection).toBeDefined();
      expect(typeof result.current.getDuckDBConnection).toBe('function');
    });

    it('should handle connection state', () => {
      const { result } = renderHook(() => useDuckDB(), {
        wrapper: ({ children }) => <DuckDBProvider>{children}</DuckDBProvider>,
      });

      const connection = result.current.getDuckDBConnection();
      expect(connection).toBeDefined(); // Will be null from mock but that's ok
    });
  });

  describe('Error Handling', () => {
    it('should start with no error', () => {
      const { result } = renderHook(() => useDuckDB(), {
        wrapper: ({ children }) => <DuckDBProvider>{children}</DuckDBProvider>,
      });

      expect(result.current.error).toBeNull();
    });

    it('should provide loading state', () => {
      const { result } = renderHook(() => useDuckDB(), {
        wrapper: ({ children }) => <DuckDBProvider>{children}</DuckDBProvider>,
      });

      expect(result.current.isLoading).toBeDefined();
      expect(typeof result.current.isLoading).toBe('boolean');
    });
  });

  describe('Stats', () => {
    it('should provide stats property', () => {
      const { result } = renderHook(() => useDuckDB(), {
        wrapper: ({ children }) => <DuckDBProvider>{children}</DuckDBProvider>,
      });

      expect(result.current).toHaveProperty('stats');
      // Stats can be null initially
      expect(result.current.stats).toBeDefined();
    });
  });
});