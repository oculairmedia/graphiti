/**
 * React hook for streaming graph data
 * Provides progressive loading with incremental rendering
 */

import { useState, useRef, useCallback, useEffect } from 'react';
import { streamingService, StreamingService } from '../services/streamingService';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';
import { logger } from '../utils/logger';
import { useGraphWorker } from './useGraphWorker';

interface StreamingState {
  nodes: GraphNode[];
  links: GraphLink[];
  isStreaming: boolean;
  progress: number;
  chunksProcessed: number;
  totalChunks: number;
  error: Error | null;
}

interface StreamingOptions {
  chunkSize?: number;
  maxNodes?: number;
  maxLinks?: number;
  useWorker?: boolean;
  onChunkReceived?: (nodes: GraphNode[], links: GraphLink[]) => void;
  onStreamComplete?: () => void;
}

export function useStreamingData(options: StreamingOptions = {}) {
  const {
    chunkSize = 1024 * 1024, // 1MB chunks
    maxNodes = 100000,
    maxLinks = 500000,
    useWorker = true,
    onChunkReceived,
    onStreamComplete
  } = options;

  const [state, setState] = useState<StreamingState>({
    nodes: [],
    links: [],
    isStreaming: false,
    progress: 0,
    chunksProcessed: 0,
    totalChunks: 0,
    error: null
  });

  const serviceRef = useRef<StreamingService>(streamingService);
  const nodeMapRef = useRef<Map<string, GraphNode>>(new Map());
  const linkSetRef = useRef<Set<string>>(new Set());
  const abortedRef = useRef(false);
  
  const { processArrowData, transformData, isReady: workerReady } = useGraphWorker();

  /**
   * Start streaming from URL
   */
  const startStreaming = useCallback(async (url: string) => {
    logger.log('[useStreamingData] Starting stream from', url);
    
    // Reset state
    setState({
      nodes: [],
      links: [],
      isStreaming: true,
      progress: 0,
      chunksProcessed: 0,
      totalChunks: 0,
      error: null
    });
    
    nodeMapRef.current.clear();
    linkSetRef.current.clear();
    abortedRef.current = false;

    try {
      await serviceRef.current.streamArrowData(url, {
        chunkSize,
        onChunk: async (chunk) => {
          if (abortedRef.current) return;
          
          // Process chunk with worker if available
          let processedChunk = chunk;
          if (useWorker && workerReady && chunk.nodes) {
            try {
              processedChunk = await transformData(chunk, { deduplicate: true });
            } catch (error) {
              logger.warn('[useStreamingData] Worker processing failed, using direct processing', error);
            }
          }
          
          // Merge nodes (deduplicate)
          const newNodes: GraphNode[] = [];
          if (processedChunk.nodes) {
            for (const node of processedChunk.nodes) {
              if (!nodeMapRef.current.has(node.id)) {
                nodeMapRef.current.set(node.id, node);
                newNodes.push(node);
              }
            }
          }
          
          // Merge links (deduplicate)
          const newLinks: GraphLink[] = [];
          if (processedChunk.edges) {
            for (const link of processedChunk.edges) {
              const linkId = `${link.source}-${link.target}-${link.edge_type || ''}`;
              if (!linkSetRef.current.has(linkId)) {
                linkSetRef.current.add(linkId);
                newLinks.push(link);
              }
            }
          }
          
          // Check limits
          if (nodeMapRef.current.size > maxNodes) {
            logger.warn('[useStreamingData] Node limit reached, stopping stream');
            serviceRef.current.abort();
            return;
          }
          
          if (linkSetRef.current.size > maxLinks) {
            logger.warn('[useStreamingData] Link limit reached, stopping stream');
            serviceRef.current.abort();
            return;
          }
          
          // Update state incrementally
          setState(prev => ({
            ...prev,
            nodes: [...prev.nodes, ...newNodes],
            links: [...prev.links, ...newLinks],
            chunksProcessed: (chunk.metadata?.chunkIndex || prev.chunksProcessed),
            totalChunks: chunk.metadata?.totalChunks || prev.totalChunks
          }));
          
          // Callback for external handling
          if (onChunkReceived) {
            onChunkReceived(newNodes, newLinks);
          }
        },
        onProgress: (progress) => {
          setState(prev => ({ ...prev, progress }));
        },
        onComplete: () => {
          setState(prev => ({ ...prev, isStreaming: false }));
          logger.log('[useStreamingData] Streaming completed', {
            totalNodes: nodeMapRef.current.size,
            totalLinks: linkSetRef.current.size
          });
          
          if (onStreamComplete) {
            onStreamComplete();
          }
        },
        onError: (error) => {
          setState(prev => ({ 
            ...prev, 
            isStreaming: false,
            error 
          }));
          logger.error('[useStreamingData] Stream error:', error);
        }
      });
    } catch (error) {
      setState(prev => ({ 
        ...prev, 
        isStreaming: false,
        error: error as Error
      }));
      logger.error('[useStreamingData] Failed to start stream:', error);
    }
  }, [chunkSize, maxNodes, maxLinks, useWorker, workerReady, transformData, onChunkReceived, onStreamComplete]);

  /**
   * Stream from DuckDB connection
   */
  const streamFromDuckDB = useCallback(async (
    connection: any,
    query: string
  ) => {
    logger.log('[useStreamingData] Starting DuckDB stream');
    
    // Reset state
    setState({
      nodes: [],
      links: [],
      isStreaming: true,
      progress: 0,
      chunksProcessed: 0,
      totalChunks: 0,
      error: null
    });
    
    nodeMapRef.current.clear();
    linkSetRef.current.clear();
    abortedRef.current = false;

    try {
      await serviceRef.current.streamDuckDBQuery(connection, query, {
        onChunk: async (chunk) => {
          if (abortedRef.current) return;
          
          // Process nodes
          const newNodes: GraphNode[] = [];
          if (chunk.nodes) {
            for (const node of chunk.nodes) {
              if (!nodeMapRef.current.has(node.id)) {
                nodeMapRef.current.set(node.id, node);
                newNodes.push(node);
              }
            }
          }
          
          // Process links
          const newLinks: GraphLink[] = [];
          if (chunk.edges) {
            for (const link of chunk.edges) {
              const linkId = `${link.source}-${link.target}`;
              if (!linkSetRef.current.has(linkId)) {
                linkSetRef.current.add(linkId);
                newLinks.push(link);
              }
            }
          }
          
          // Update state
          setState(prev => ({
            ...prev,
            nodes: [...prev.nodes, ...newNodes],
            links: [...prev.links, ...newLinks],
            chunksProcessed: prev.chunksProcessed + 1
          }));
          
          if (onChunkReceived) {
            onChunkReceived(newNodes, newLinks);
          }
        },
        onProgress: (count) => {
          setState(prev => ({ ...prev, progress: count }));
        },
        onComplete: () => {
          setState(prev => ({ ...prev, isStreaming: false }));
          
          if (onStreamComplete) {
            onStreamComplete();
          }
        },
        onError: (error) => {
          setState(prev => ({ 
            ...prev, 
            isStreaming: false,
            error 
          }));
        }
      });
    } catch (error) {
      setState(prev => ({ 
        ...prev, 
        isStreaming: false,
        error: error as Error
      }));
    }
  }, [onChunkReceived, onStreamComplete]);

  /**
   * Abort active stream
   */
  const abortStream = useCallback(() => {
    abortedRef.current = true;
    serviceRef.current.abort();
    setState(prev => ({ ...prev, isStreaming: false }));
    logger.log('[useStreamingData] Stream aborted by user');
  }, []);

  /**
   * Clear all data
   */
  const clearData = useCallback(() => {
    nodeMapRef.current.clear();
    linkSetRef.current.clear();
    setState({
      nodes: [],
      links: [],
      isStreaming: false,
      progress: 0,
      chunksProcessed: 0,
      totalChunks: 0,
      error: null
    });
  }, []);

  /**
   * Get current statistics
   */
  const getStats = useCallback(() => {
    return {
      totalNodes: nodeMapRef.current.size,
      totalLinks: linkSetRef.current.size,
      chunksProcessed: state.chunksProcessed,
      progress: state.progress,
      isStreaming: state.isStreaming,
      memoryUsage: {
        nodes: nodeMapRef.current.size * 200, // Estimate 200 bytes per node
        links: linkSetRef.current.size * 50   // Estimate 50 bytes per link
      }
    };
  }, [state]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (state.isStreaming) {
        serviceRef.current.abort();
      }
    };
  }, [state.isStreaming]);

  return {
    // State
    nodes: state.nodes,
    links: state.links,
    isStreaming: state.isStreaming,
    progress: state.progress,
    chunksProcessed: state.chunksProcessed,
    totalChunks: state.totalChunks,
    error: state.error,
    
    // Actions
    startStreaming,
    streamFromDuckDB,
    abortStream,
    clearData,
    
    // Utils
    getStats
  };
}