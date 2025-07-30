import { useState, useEffect, useRef, useCallback } from 'react';
import type { GraphNode, GraphEdge } from '../types/graph';
import { transformNodes, transformLinks } from '../utils/graphDataTransform';
import { logger } from '../utils/logger';

interface CosmographData {
  points: GraphNode[];
  links: GraphEdge[];
  cosmographConfig: Record<string, unknown>;
}

export function useGraphData(nodes: GraphNode[], links: GraphEdge[]) {
  const [cosmographData, setCosmographData] = useState<CosmographData | null>(null);
  const [currentNodes, setCurrentNodes] = useState<GraphNode[]>([]);
  const [currentLinks, setCurrentLinks] = useState<GraphEdge[]>([]);
  const [isDataPreparing, setIsDataPreparing] = useState(false);
  const [dataKitError, setDataKitError] = useState<string | null>(null);
  
  // Track if we're doing an incremental update
  const isIncrementalUpdateRef = useRef(false);
  
  // DataKit config (stable to prevent reprocessing)
  const dataKitConfig = {
    points: {
      pointIdBy: 'id',
      pointIndexBy: 'index',
      pointLabelBy: 'label',
      pointColorBy: 'node_type',
      pointIncludeColumns: ['created_at', 'created_at_timestamp']
    },
    links: {
      linkSourceBy: 'source',
      linkSourceIndexBy: 'sourceIndex',
      linkTargetBy: 'target',
      linkTargetIndexBy: 'targetIndex',
      linkColorBy: 'edge_type',
      linkWidthBy: 'weight',
      linkIncludeColumns: ['created_at', 'updated_at']
    }
  };
  
  // Update current nodes and links when props change
  useEffect(() => {
    setCurrentNodes(nodes);
    setCurrentLinks(links);
  }, [nodes, links]);
  
  // Data preparation effect
  useEffect(() => {
    // Skip if we're doing an incremental update
    if (isIncrementalUpdateRef.current) {
      return;
    }
    
    if (!nodes || !links || nodes.length === 0) {
      setCosmographData(null);
      setDataKitError(null);
      return;
    }
    
    let cancelled = false;
    
    const prepareData = async () => {
      try {
        setIsDataPreparing(true);
        setDataKitError(null);
        
        // Transform data
        const transformedNodes = transformNodes(nodes);
        const transformedLinks = transformLinks(links, transformedNodes);
        
        // Log node type distribution
        const nodeTypeDistribution = transformedNodes.reduce((acc, node) => {
          acc[node.node_type] = (acc[node.node_type] || 0) + 1;
          return acc;
        }, {} as Record<string, number>);
        
        logger.log('useGraphData: Node type distribution:', nodeTypeDistribution);
        logger.log('useGraphData: Transformed data -', 
          'nodes:', transformedNodes.length, 
          'links:', transformedLinks.length
        );
        
        if (transformedNodes.length === 0) {
          throw new Error('No valid nodes found after transformation');
        }
        
        if (!cancelled) {
          setCosmographData({
            points: transformedNodes,
            links: transformedLinks,
            cosmographConfig: dataKitConfig
          });
        }
      } catch (error) {
        if (!cancelled) {
          const errorMessage = error instanceof Error ? error.message : 'Unknown error';
          logger.error('useGraphData: Data preparation failed:', errorMessage);
          setDataKitError(errorMessage);
          
          // Fallback to empty data
          setCosmographData({
            points: [],
            links: [],
            cosmographConfig: {}
          });
        }
      } finally {
        if (!cancelled) {
          setIsDataPreparing(false);
        }
      }
    };
    
    prepareData();
    
    return () => {
      cancelled = true;
    };
  }, [nodes, links]);
  
  return {
    cosmographData,
    currentNodes,
    currentLinks,
    isDataPreparing,
    dataKitError,
    setCurrentNodes,
    setCurrentLinks,
    isIncrementalUpdateRef
  };
}