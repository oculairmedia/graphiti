import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '../test/utils';
import { useGraphDataQuery } from './useGraphDataQuery';

// Mock the API client
vi.mock('../api/graphClient', () => ({
  graphClient: {
    getGraphData: vi.fn().mockResolvedValue({
      nodes: [],
      edges: [],
    }),
  },
}));

describe('useGraphDataQuery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Data Fetching', () => {
    it('should fetch graph data successfully', async () => {
      const { result } = renderHook(() => useGraphDataQuery());

      // Hook should return expected properties
      expect(result.current).toHaveProperty('data');
      expect(result.current).toHaveProperty('isLoading');
      expect(result.current).toHaveProperty('error');
      expect(result.current).toHaveProperty('transformedData');
      
      // Error should be null
      expect(result.current.error).toBeNull();
    });

    it('should handle empty response', async () => {
      const { result } = renderHook(() => useGraphDataQuery());

      // Data should be available immediately or after loading
      await waitFor(() => {
        expect(result.current.data).toBeDefined();
      });

      expect(result.current.error).toBeNull();
    });
  });

  describe('Data Transformation', () => {
    it('should transform data correctly', async () => {
      const { result } = renderHook(() => useGraphDataQuery());

      await waitFor(() => {
        expect(result.current.transformedData).toBeDefined();
      });

      expect(result.current.transformedData).toHaveProperty('nodes');
      expect(result.current.transformedData).toHaveProperty('links');
    });
  });

  describe('Incremental Updates', () => {
    it('should track incremental update state', async () => {
      const { result } = renderHook(() => useGraphDataQuery());

      await waitFor(() => {
        expect(result.current.isIncrementalUpdate).toBeDefined();
      });

      expect(result.current.isIncrementalUpdate).toBe(false);
      expect(result.current.isGraphInitialized).toBeDefined();
    });
  });

  describe('Data Diff', () => {
    it('should provide data diff information', async () => {
      const { result } = renderHook(() => useGraphDataQuery());

      await waitFor(() => {
        expect(result.current.dataDiff).toBeDefined();
      });

      expect(result.current.dataDiff).toHaveProperty('hasChanges');
      expect(result.current.dataDiff).toHaveProperty('addedNodes');
      expect(result.current.dataDiff).toHaveProperty('removedNodeIds');
      expect(result.current.dataDiff).toHaveProperty('updatedNodes');
    });
  });

  describe('DuckDB Integration', () => {
    it('should have refreshDuckDBData function', async () => {
      const { result } = renderHook(() => useGraphDataQuery());

      await waitFor(() => {
        expect(result.current.refreshDuckDBData).toBeDefined();
      });

      expect(typeof result.current.refreshDuckDBData).toBe('function');
    });
  });
});