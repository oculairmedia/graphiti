import React, { forwardRef } from 'react';
import '../styles/cosmograph.css';

import { useGraphCanvasOrchestration } from '../hooks/useGraphCanvasOrchestration';
import { GraphCanvasRenderer } from './GraphCanvasRenderer';
import { ProgressiveLoadingOverlay } from './ProgressiveLoadingOverlay';
import { GraphOverlays } from './GraphOverlays';

import type { GraphCanvasHandle } from '../types/graphCanvas';
import type { GraphCanvasComponentProps } from '../types/graphCanvasV2Types';

export type { GraphCanvasComponentProps };

const GraphCanvasV2 = forwardRef<GraphCanvasHandle, GraphCanvasComponentProps>(
  (props, ref) => {
    const {
      cosmographRef,
      cosmographData,
      config,
      visualConfig,
      eventHandlers,
      containerStyle,
      loading,
      error,
      statistics,
      liveNodeCount,
      liveEdgeCount,
      fps,
      glowingNodesSize,
      loadingPhase,
      loadingProgress,
      setIsReady,
      setIsCanvasReady,
    } = useGraphCanvasOrchestration(props, ref);

    if (loading || !cosmographData) {
      return (
        <div className="flex items-center justify-center h-full">
          <div className="text-gray-500">Loading graph data...</div>
        </div>
      );
    }

    if (error) {
      return (
        <div className="flex items-center justify-center h-full">
          <div className="text-red-500">Error loading graph: {error instanceof Error ? error.message : String(error)}</div>
        </div>
      );
    }

    return (
      <div className={props.className} style={containerStyle}>
        {loadingPhase && (
          <ProgressiveLoadingOverlay
            phase={loadingPhase}
            loaded={loadingProgress.loaded}
            total={loadingProgress.total}
            isVisible={!!loadingPhase}
          />
        )}

        <GraphOverlays
          nodeCount={statistics.nodeCount}
          edgeCount={statistics.edgeCount}
          liveNodeCount={liveNodeCount}
          liveEdgeCount={liveEdgeCount}
          fps={fps}
          visibleNodes={cosmographData?.nodes?.length}
          selectedNodes={props.selectedNodes?.length ?? 0}
        />

        <GraphCanvasRenderer
          cosmographRef={cosmographRef}
          cosmographData={cosmographData}
          config={config}
          visualConfig={visualConfig}
          eventHandlers={eventHandlers}
          hasGlowingNodes={glowingNodesSize > 0}
          onReady={() => {
            setIsReady(true);
            setIsCanvasReady(true);
            if (cosmographRef.current && cosmographData && cosmographData.nodes.length > 0) {
              props.onContextReady?.(true);
            }
          }}
        />
      </div>
    );
  },
);

GraphCanvasV2.displayName = 'GraphCanvasV2';

export default GraphCanvasV2;
