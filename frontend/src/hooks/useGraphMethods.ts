import { useCallback, MutableRefObject } from 'react';
import type { GraphNode, GraphEdge } from '../types/graph';
import { transformDataForUpdate } from '../utils/graphDataTransform';
import { logger } from '../utils/logger';

interface GraphMethodsProps {
  cosmographRef: MutableRefObject<any>;
  currentNodes: GraphNode[];
  currentLinks: GraphEdge[];
  setCurrentNodes: (nodes: GraphNode[]) => void;
  setCurrentLinks: (links: GraphEdge[]) => void;
  isIncrementalUpdateRef: MutableRefObject<boolean>;
}

export function useGraphMethods({
  cosmographRef,
  currentNodes,
  currentLinks,
  setCurrentNodes,
  setCurrentLinks,
  isIncrementalUpdateRef
}: GraphMethodsProps) {
  
  // Update data incrementally
  const updateDataIncrementally = useCallback(async (
    updatedNodes: GraphNode[], 
    updatedLinks: GraphEdge[], 
    runSimulation = true
  ) => {
    if (!cosmographRef.current?.setData) {
      logger.warn('Cosmograph ref not ready for incremental update');
      return;
    }
    
    try {
      isIncrementalUpdateRef.current = true;
      setCurrentNodes(updatedNodes);
      setCurrentLinks(updatedLinks);
      
      // Transform and use Cosmograph's setData directly
      if (updatedNodes.length > 0) {
        const { nodes: transformedNodes, links: transformedLinks } = 
          transformDataForUpdate(updatedNodes, updatedLinks);
        
        cosmographRef.current.setData(transformedNodes, transformedLinks, runSimulation);
      }
    } catch (error) {
      logger.error('Incremental data update failed:', error);
    } finally {
      setTimeout(() => {
        isIncrementalUpdateRef.current = false;
      }, 100);
    }
  }, [cosmographRef, setCurrentNodes, setCurrentLinks, isIncrementalUpdateRef]);
  
  // Add node
  const addNode = useCallback(async (node: GraphNode, links: GraphEdge[] = []) => {
    if (!cosmographRef.current?.setData) return;
    
    try {
      isIncrementalUpdateRef.current = true;
      
      const newNodes = [...currentNodes, node];
      const newLinks = [...currentLinks, ...links];
      
      setCurrentNodes(newNodes);
      setCurrentLinks(newLinks);
      
      const { nodes: transformedNodes, links: transformedLinks } = 
        transformDataForUpdate(newNodes, newLinks);
      
      cosmographRef.current.setData(transformedNodes, transformedLinks, false);
    } catch (error) {
      logger.error('Node addition failed:', error);
    } finally {
      setTimeout(() => {
        isIncrementalUpdateRef.current = false;
      }, 100);
    }
  }, [currentNodes, currentLinks, cosmographRef, setCurrentNodes, setCurrentLinks, isIncrementalUpdateRef]);
  
  // Remove node
  const removeNode = useCallback(async (nodeId: string) => {
    if (!cosmographRef.current?.setData) return;
    
    try {
      isIncrementalUpdateRef.current = true;
      
      const newNodes = currentNodes.filter(n => n.id !== nodeId);
      const newLinks = currentLinks.filter(l => l.source !== nodeId && l.target !== nodeId);
      
      setCurrentNodes(newNodes);
      setCurrentLinks(newLinks);
      
      const { nodes: transformedNodes, links: transformedLinks } = 
        transformDataForUpdate(newNodes, newLinks);
      
      cosmographRef.current.setData(transformedNodes, transformedLinks, false);
    } catch (error) {
      logger.error('Node removal failed:', error);
    } finally {
      setTimeout(() => {
        isIncrementalUpdateRef.current = false;
      }, 100);
    }
  }, [currentNodes, currentLinks, cosmographRef, setCurrentNodes, setCurrentLinks, isIncrementalUpdateRef]);
  
  // Remove nodes (batch)
  const removeNodes = useCallback(async (nodeIds: string[]) => {
    if (!cosmographRef.current?.setData) return;
    
    try {
      isIncrementalUpdateRef.current = true;
      
      const nodeIdSet = new Set(nodeIds);
      const filteredNodes = currentNodes.filter(node => !nodeIdSet.has(node.id));
      const filteredLinks = currentLinks.filter(link => 
        !nodeIdSet.has(link.source) && !nodeIdSet.has(link.target)
      );
      
      setCurrentNodes(filteredNodes);
      setCurrentLinks(filteredLinks);
      
      const { nodes: transformedNodes, links: transformedLinks } = 
        transformDataForUpdate(filteredNodes, filteredLinks);
      
      cosmographRef.current.setData(transformedNodes, transformedLinks, false);
    } catch (error) {
      logger.error('Node removal failed:', error);
    } finally {
      setTimeout(() => {
        isIncrementalUpdateRef.current = false;
      }, 100);
    }
  }, [currentNodes, currentLinks, cosmographRef, setCurrentNodes, setCurrentLinks, isIncrementalUpdateRef]);
  
  // Remove links
  const removeLinks = useCallback(async (linkIds: string[]) => {
    if (!cosmographRef.current?.setData) return;
    
    try {
      isIncrementalUpdateRef.current = true;
      
      const linkIdSet = new Set(linkIds);
      const filteredLinks = currentLinks.filter(link => {
        const linkId = `${link.source}-${link.target}`;
        return !linkIdSet.has(linkId);
      });
      
      setCurrentLinks(filteredLinks);
      
      const { nodes: transformedNodes, links: transformedLinks } = 
        transformDataForUpdate(currentNodes, filteredLinks);
      
      cosmographRef.current.setData(transformedNodes, transformedLinks, false);
    } catch (error) {
      logger.error('Link removal failed:', error);
    } finally {
      setTimeout(() => {
        isIncrementalUpdateRef.current = false;
      }, 100);
    }
  }, [currentLinks, currentNodes, cosmographRef, setCurrentLinks, isIncrementalUpdateRef]);
  
  return {
    updateDataIncrementally,
    addNode,
    removeNode,
    removeNodes,
    removeLinks
  };
}