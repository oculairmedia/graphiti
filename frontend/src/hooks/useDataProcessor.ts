import { useRef, useCallback, useEffect } from 'react';
import { logger } from '../utils/logger';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';

interface ProcessDataOptions {
  nodes: GraphNode[];
  links: GraphLink[];
  filterConfig?: Record<string, unknown>;
}

interface ProcessDataResult {
  nodes: GraphNode[];
  links: GraphLink[];
  nodeIndexMap?: Map<string, number>;
}

export function useDataProcessor() {
  const workerRef = useRef<Worker | null>(null);
  const processingRef = useRef(false);
  
  // Initialize worker
  useEffect(() => {
    try {
      // Create worker with inline code to avoid build issues
      const workerCode = `
        // Reusable node transformation logic
        function transformNode(node, index) {
          const createdAt = node.properties?.created_at || node.created_at || node.properties?.created || null;
          const degree = Number(node.properties?.degree_centrality || 0);
          
          return {
            id: String(node.id),
            index: index,
            label: String(node.label || node.id),
            node_type: String(node.node_type || 'Unknown'),
            centrality: Number(node.properties?.degree_centrality || node.properties?.pagerank_centrality || node.size || 1),
            cluster: String(node.node_type || 'Unknown'),
            clusterStrength: 0.7,
            degree_centrality: degree,
            pagerank_centrality: Number(node.properties?.pagerank_centrality || 0),
            betweenness_centrality: Number(node.properties?.betweenness_centrality || 0),
            eigenvector_centrality: Number(node.properties?.eigenvector_centrality || 0),
            created_at: createdAt,
            created_at_timestamp: createdAt ? new Date(createdAt).getTime() : null,
            properties: node.properties,
            size: node.size,
            x: node.x,
            y: node.y
          };
        }

        // Reusable link transformation logic
        function transformLink(link, nodeIndexMap) {
          const sourceIndex = nodeIndexMap.get(String(link.source || link.from));
          const targetIndex = nodeIndexMap.get(String(link.target || link.to));
          
          if (sourceIndex === undefined || targetIndex === undefined) {
            return null;
          }
          
          return {
            source: String(link.source || link.from),
            sourceIndex: sourceIndex,
            target: String(link.target || link.to),
            targetIndex: targetIndex,
            edge_type: String(link.edge_type || 'default'),
            weight: Number(link.weight || 1),
            created_at: link.created_at,
            updated_at: link.updated_at
          };
        }

        // Process large datasets in chunks to avoid blocking
        async function processDataInChunks(nodes, links) {
          const CHUNK_SIZE = 1000;
          const transformedNodes = [];
          const nodeIndexMap = new Map();
          
          // Process nodes in chunks
          for (let i = 0; i < nodes.length; i += CHUNK_SIZE) {
            const chunk = nodes.slice(i, i + CHUNK_SIZE);
            const transformed = chunk.map((node, idx) => {
              const globalIndex = i + idx;
              const transformedNode = transformNode(node, globalIndex);
              nodeIndexMap.set(transformedNode.id, globalIndex);
              return transformedNode;
            });
            transformedNodes.push(...transformed);
            
            // Yield to allow other operations
            if (i % (CHUNK_SIZE * 10) === 0) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
          }
          
          // Process links in chunks
          const transformedLinks = [];
          for (let i = 0; i < links.length; i += CHUNK_SIZE) {
            const chunk = links.slice(i, i + CHUNK_SIZE);
            const transformed = chunk
              .map(link => transformLink(link, nodeIndexMap))
              .filter(Boolean);
            transformedLinks.push(...transformed);
            
            // Yield to allow other operations
            if (i % (CHUNK_SIZE * 10) === 0) {
              await new Promise(resolve => setTimeout(resolve, 0));
            }
          }
          
          return {
            nodes: transformedNodes,
            links: transformedLinks,
            nodeIndexMap: Array.from(nodeIndexMap.entries())
          };
        }

        // Handle messages from main thread
        self.addEventListener('message', async (event) => {
          const { type, data } = event.data;
          
          switch (type) {
            case 'TRANSFORM_DATA':
              try {
                const result = await processDataInChunks(data.nodes, data.links);
                self.postMessage({
                  type: 'DATA_TRANSFORMED',
                  data: result
                });
              } catch (error) {
                self.postMessage({
                  type: 'ERROR',
                  error: error instanceof Error ? error.message : 'Unknown error'
                });
              }
              break;
          }
        });
      `;
      
      const blob = new Blob([workerCode], { type: 'application/javascript' });
      const workerUrl = URL.createObjectURL(blob);
      workerRef.current = new Worker(workerUrl);
      
      // Clean up blob URL after worker is created
      URL.revokeObjectURL(workerUrl);
      
      logger.log('Data processor worker initialized');
    } catch (error) {
      logger.error('Failed to initialize data processor worker:', error);
    }
    
    return () => {
      if (workerRef.current) {
        workerRef.current.terminate();
        workerRef.current = null;
      }
    };
  }, []);
  
  const processData = useCallback(async (options: ProcessDataOptions): Promise<ProcessDataResult> => {
    if (!workerRef.current) {
      logger.warn('Worker not initialized, processing in main thread');
      // Fallback to main thread processing
      return options;
    }
    
    if (processingRef.current) {
      logger.warn('Data processing already in progress');
      return options;
    }
    
    // For small datasets, process in main thread
    if (options.nodes.length < 1000) {
      return options;
    }
    
    processingRef.current = true;
    
    return new Promise((resolve, reject) => {
      const handleMessage = (event: MessageEvent) => {
        const { type, data, error } = event.data;
        
        switch (type) {
          case 'DATA_TRANSFORMED':
            // Convert array back to Map
            if (data.nodeIndexMap) {
              data.nodeIndexMap = new Map(data.nodeIndexMap);
            }
            processingRef.current = false;
            resolve(data);
            break;
            
          case 'ERROR':
            processingRef.current = false;
            reject(new Error(error));
            break;
        }
      };
      
      const handleError = (error: ErrorEvent) => {
        processingRef.current = false;
        reject(error);
      };
      
      workerRef.current!.addEventListener('message', handleMessage);
      workerRef.current!.addEventListener('error', handleError);
      
      // Send data to worker
      workerRef.current!.postMessage({
        type: 'TRANSFORM_DATA',
        data: options
      });
      
      // Cleanup listeners after processing
      const cleanup = () => {
        if (workerRef.current) {
          workerRef.current.removeEventListener('message', handleMessage);
          workerRef.current.removeEventListener('error', handleError);
        }
      };
      
      // Set timeout for worker processing
      const timeout = setTimeout(() => {
        cleanup();
        processingRef.current = false;
        reject(new Error('Data processing timeout'));
      }, 30000); // 30 second timeout
      
      // Clear timeout on success/error
      const originalResolve = resolve;
      const originalReject = reject;
      
      resolve = (value) => {
        clearTimeout(timeout);
        cleanup();
        originalResolve(value);
      };
      
      reject = (error) => {
        clearTimeout(timeout);
        cleanup();
        originalReject(error);
      };
    });
  }, []);
  
  return {
    processData,
    isProcessing: processingRef.current
  };
}