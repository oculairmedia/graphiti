import { useCallback, useRef } from 'react';
import { logger } from '../utils/logger';

interface CosmographRef {
  setZoomLevel: (level: number, duration?: number) => void;
  getZoomLevel: () => number;
  fitView: (duration?: number, padding?: number) => void;
  fitViewByPointIndices: (indices: number[], duration?: number, padding?: number) => void;
  zoomToPoint: (index: number, duration?: number, scale?: number, canZoomOut?: boolean) => void;
  trackPointPositionsByIndices: (indices: number[]) => void;
  getTrackedPointPositionsMap: () => Map<number, [number, number]> | undefined;
  getTrackedPointPositionsArray: () => Float32Array | undefined;
}

interface ZoomConfig {
  fitViewDuration: number;
  fitViewPadding: number;
  zoomFactor?: number;
  minZoom?: number;
  maxZoom?: number;
}

export function useGraphZoom(
  cosmographRef: React.RefObject<CosmographRef | null>,
  config: ZoomConfig,
  dependencies?: {
    isCanvasReady?: boolean;
    hasData?: boolean;
  }
) {
  const { fitViewDuration, fitViewPadding, zoomFactor = 1.5, minZoom = 0.1, maxZoom = 10 } = config;
  const { isCanvasReady = true, hasData = true } = dependencies || {};

  const zoomIn = useCallback(() => {
    if (!cosmographRef.current) return;
    
    try {
      const currentZoom = cosmographRef.current.getZoomLevel();
      if (currentZoom !== undefined) {
        const newZoom = Math.min(currentZoom * zoomFactor, maxZoom);
        cosmographRef.current.setZoomLevel(newZoom, fitViewDuration);
        logger.log(`Zoomed in from ${currentZoom} to ${newZoom}`);
      } else {
        logger.warn('Could not get current zoom level for zoom in');
      }
    } catch (error) {
      logger.warn('Zoom in failed:', error);
    }
  }, [cosmographRef, fitViewDuration, zoomFactor, maxZoom]);

  const zoomOut = useCallback(() => {
    if (!cosmographRef.current) return;
    
    try {
      const currentZoom = cosmographRef.current.getZoomLevel();
      if (currentZoom !== undefined) {
        const newZoom = Math.max(currentZoom / zoomFactor, minZoom);
        cosmographRef.current.setZoomLevel(newZoom, fitViewDuration);
        logger.log(`Zoomed out from ${currentZoom} to ${newZoom}`);
      } else {
        logger.warn('Could not get current zoom level for zoom out');
      }
    } catch (error) {
      logger.warn('Zoom out failed:', error);
    }
  }, [cosmographRef, fitViewDuration, zoomFactor, minZoom]);

  const fitView = useCallback(() => {
    if (!cosmographRef.current) return;
    
    // Ensure canvas is ready
    if (!isCanvasReady) {
      logger.warn('Cannot fitView - canvas not ready');
      return;
    }
    
    // Ensure we have data
    if (!hasData) {
      logger.warn('Cannot fitView - no data');
      return;
    }
    
    try {
      logger.log('Calling fitView with duration:', fitViewDuration, 'padding:', fitViewPadding);
      cosmographRef.current.fitView(fitViewDuration, fitViewPadding);
    } catch (error) {
      logger.warn('Fit view failed:', error);
    }
  }, [cosmographRef, fitViewDuration, fitViewPadding, isCanvasReady, hasData]);

  const fitViewByPointIndices = useCallback((indices: number[], duration?: number, padding?: number) => {
    if (!cosmographRef.current || indices.length === 0) return;
    
    try {
      const actualDuration = duration !== undefined ? duration : fitViewDuration;
      const actualPadding = padding !== undefined ? padding : fitViewPadding;
      cosmographRef.current.fitViewByPointIndices(indices, actualDuration, actualPadding);
      logger.log(`Fit view to ${indices.length} nodes`);
    } catch (error) {
      logger.warn('Fit view by indices failed:', error);
    }
  }, [cosmographRef, fitViewDuration, fitViewPadding]);

  const zoomToPoint = useCallback((
    index: number, 
    duration?: number, 
    scale?: number, 
    canZoomOut?: boolean
  ) => {
    if (!cosmographRef.current) return;
    
    try {
      const actualDuration = duration !== undefined ? duration : fitViewDuration;
      const actualScale = scale !== undefined ? scale : 6.0; // Good zoom scale for detailed focus
      const actualCanZoomOut = canZoomOut !== undefined ? canZoomOut : true;
      
      cosmographRef.current.zoomToPoint(index, actualDuration, actualScale, actualCanZoomOut);
      logger.log(`Zoomed to point at index ${index}`);
    } catch (error) {
      logger.warn('Zoom to point failed:', error);
    }
  }, [cosmographRef, fitViewDuration]);

  const trackPointPositionsByIndices = useCallback((indices: number[]) => {
    if (!cosmographRef.current || indices.length === 0) return;
    
    try {
      cosmographRef.current.trackPointPositionsByIndices(indices);
    } catch (error) {
      logger.warn('Track point positions failed:', error);
    }
  }, [cosmographRef]);

  const getTrackedPointPositionsMap = useCallback(() => {
    if (!cosmographRef.current) return undefined;
    
    try {
      return cosmographRef.current.getTrackedPointPositionsMap();
    } catch (error) {
      logger.warn('Get tracked positions failed:', error);
      return undefined;
    }
  }, [cosmographRef]);

  const getZoomLevel = useCallback(() => {
    if (!cosmographRef.current) return 1;
    
    try {
      return cosmographRef.current.getZoomLevel() || 1;
    } catch (error) {
      logger.warn('Get zoom level failed:', error);
      return 1;
    }
  }, [cosmographRef]);

  const setZoomLevel = useCallback((level: number, duration?: number) => {
    if (!cosmographRef.current) return;
    
    try {
      const clampedLevel = Math.max(minZoom, Math.min(maxZoom, level));
      const actualDuration = duration !== undefined ? duration : fitViewDuration;
      cosmographRef.current.setZoomLevel(clampedLevel, actualDuration);
      logger.log(`Set zoom level to ${clampedLevel}`);
    } catch (error) {
      logger.warn('Set zoom level failed:', error);
    }
  }, [cosmographRef, fitViewDuration, minZoom, maxZoom]);

  return {
    zoomIn,
    zoomOut,
    fitView,
    fitViewByPointIndices,
    zoomToPoint,
    trackPointPositionsByIndices,
    getTrackedPointPositionsMap,
    getZoomLevel,
    setZoomLevel,
  };
}