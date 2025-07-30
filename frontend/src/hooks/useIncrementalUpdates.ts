import { useEffect, useRef } from 'react';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';

interface GraphCanvasHandle {
  setIncrementalUpdateFlag: (enabled: boolean) => void;
  removeNodes: (nodeIds: string[]) => void;
  removeLinks: (linkIds: string[]) => void;
  updateNodes: (updatedNodes: GraphNode[]) => void;
  updateLinks: (updatedLinks: GraphLink[]) => void;
  addIncrementalData: (newNodes: GraphNode[], newLinks: GraphLink[], runSimulation?: boolean) => void;
  resumeSimulation: () => void;
}

interface DataDiff {
  hasChanges: boolean;
  isInitialLoad: boolean;
  changeCount: number;
  removedNodeIds: string[];
  removedLinkIds: string[];
  updatedNodes: GraphNode[];
  updatedLinks: GraphLink[];
  addedNodes: GraphNode[];
  addedLinks: GraphLink[];
}

export function useIncrementalUpdates(
  graphCanvasRef: React.RefObject<GraphCanvasHandle>,
  dataDiff: DataDiff,
  isGraphInitialized: boolean,
  isIncrementalUpdate: boolean,
  setIsIncrementalUpdate: (value: boolean) => void,
  data: GraphData | null,
  stableDataRef: React.MutableRefObject<{ nodes: GraphNode[], edges: GraphLink[] } | null>
) {
  // Handle incremental updates when changes are detected (skip initial loads)
  useEffect(() => {
    // Skip if no changes, no ref available, initial load, or graph not initialized
    if (!dataDiff.hasChanges || !graphCanvasRef.current || dataDiff.isInitialLoad || !isGraphInitialized) {
      return;
    }

    // Ensure we have stable data from previous state
    if (!stableDataRef.current) {
      return;
    }

    const applyIncrementalUpdates = async () => {
      // Set flags BEFORE triggering React re-render to prevent Data Kit processing
      if (graphCanvasRef.current?.setIncrementalUpdateFlag) {
        graphCanvasRef.current.setIncrementalUpdateFlag(true);
      }
      
      setIsIncrementalUpdate(true);

      try {
        // Apply changes in order: removals first, then updates, then additions
        if (dataDiff.removedNodeIds.length > 0) {
          await graphCanvasRef.current!.removeNodes(dataDiff.removedNodeIds);
        }

        if (dataDiff.removedLinkIds.length > 0) {
          await graphCanvasRef.current!.removeLinks(dataDiff.removedLinkIds);
        }

        if (dataDiff.updatedNodes.length > 0) {
          await graphCanvasRef.current!.updateNodes(dataDiff.updatedNodes);
        }

        if (dataDiff.updatedLinks.length > 0) {
          await graphCanvasRef.current!.updateLinks(dataDiff.updatedLinks);
        }

        if (dataDiff.addedNodes.length > 0 || dataDiff.addedLinks.length > 0) {
          // Transform added links to have source/target format
          const transformedAddedLinks = dataDiff.addedLinks.map(link => ({
            ...link,
            source: link.from,
            target: link.to
          }));
          
          await graphCanvasRef.current!.addIncrementalData(
            dataDiff.addedNodes, 
            transformedAddedLinks, 
            false // Don't restart simulation for small additions
          );
          
          // Resume simulation after incremental data changes, with proper timing
          setTimeout(() => {
            if (graphCanvasRef.current?.resumeSimulation) {
              graphCanvasRef.current.resumeSimulation();
            }
          }, 100); // Small delay to ensure component has updated
        }

        // Update stable data reference
        if (data) {
          stableDataRef.current = { nodes: [...data.nodes], edges: [...data.edges] };
        }

      } catch (error) {
        // Fallback to full reload on error
        setIsIncrementalUpdate(false);
      }
    };

    applyIncrementalUpdates();
  }, [dataDiff.hasChanges, dataDiff.changeCount, dataDiff.isInitialLoad, isGraphInitialized, data, graphCanvasRef, setIsIncrementalUpdate, stableDataRef]);
}