import React, { forwardRef, useImperativeHandle, useRef, useCallback, useEffect, useState, memo } from 'react';
import { CosmographTimeline, useCosmograph } from '@cosmograph/react';
import type { CosmographTimelineRef } from '@cosmograph/react';
import { Play, Pause, RotateCcw, ChevronDown, ChevronUp, SkipForward, Clock, Calendar, ZoomIn, ZoomOut, Maximize2, Camera, Trash2, Pin, Eye, Download, Move } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { useGraphZoom } from '../hooks/useGraphZoom';


interface GraphTimelineProps {
  onTimeRangeChange?: (range: [Date, Date] | [number, number] | undefined) => void;
  className?: string;
  isVisible?: boolean;
  onVisibilityChange?: (visible: boolean) => void;
  cosmographRef?: React.RefObject<any>;
  selectedCount?: number;
  onClearSelection?: () => void;
  onScreenshot?: () => void;
}

export interface GraphTimelineHandle {
  setSelection: (range?: [Date, Date] | [number, number]) => void;
  playAnimation: () => void;
  pauseAnimation: () => void;
  stopAnimation: () => void;
  toggleVisibility: () => void;
}

export const GraphTimeline = forwardRef<GraphTimelineHandle, GraphTimelineProps>(
  ({ onTimeRangeChange, className = '', isVisible = true, onVisibilityChange, cosmographRef, selectedCount = 0, onClearSelection, onScreenshot, updateMode = 'instant' }, ref) => {
    const timelineRef = useRef<CosmographTimelineRef>(null);
    const cosmograph = useCosmograph();
    
    // The CosmographTimeline component will access data internally through the context
    // It uses the accessor="created_at_timestamp" prop to find the timestamp field
    const [isAnimating, setIsAnimating] = useState(false);
    const [isCosmographReady, setIsCosmographReady] = useState(false);
    
    // Get zoom controls from the hook
    const { zoomIn, zoomOut, fitView } = useGraphZoom(
      cosmographRef || { current: null },
      {
        fitViewDuration: 750,
        fitViewPadding: 0.2,  // Normalized value (0-1), not pixels - 0.2 = 20% padding
        zoomFactor: 1.5,
      }
    );
    const [selectedRange, setSelectedRange] = useState<[Date, Date] | [number, number] | undefined>();
    const [hasTemporalData, setHasTemporalData] = useState(false);
    const [isExpanded, setIsExpanded] = useState(true);
    const [animationSpeed, setAnimationSpeed] = useState(200);
    const [isLooping, setIsLooping] = useState(false);
    const [currentTimeWindow, setCurrentTimeWindow] = useState<string>('');
    const tickCheckInterval = useRef<NodeJS.Timeout | null>(null);

    // Check if cosmograph is available through ref or context
    useEffect(() => {
      // Try to get the actual Cosmograph ref from the GraphCanvas handle
      let actualCosmographRef = null;
      if (cosmographRef?.current?.getCosmographRef) {
        actualCosmographRef = cosmographRef.current.getCosmographRef();
      }
      
      const hasCosmo = !!(actualCosmographRef?.current || cosmograph);
      setIsCosmographReady(hasCosmo);
      
      if (hasCosmo) {
        setHasTemporalData(true);
      }
    }, [cosmographRef, cosmograph]); // Use stable deps
    
    // Cleanup interval on unmount
    useEffect(() => {
      return () => {
        if (tickCheckInterval.current) {
          clearInterval(tickCheckInterval.current);
        }
      };
    }, []);

    // Handle timeline selection
    const handleSelection = useCallback((selection?: [number, number] | [Date, Date], isManual?: boolean) => {
      setSelectedRange(selection);
      onTimeRangeChange?.(selection);
      
      if (selection) {
        // Format time window display
        const start = selection[0] instanceof Date ? selection[0] : new Date(selection[0]);
        const end = selection[1] instanceof Date ? selection[1] : new Date(selection[1]);
        const formatDate = (date: Date) => date.toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
          year: 'numeric'
        });
        setCurrentTimeWindow(`${formatDate(start)} - ${formatDate(end)}`);
      } else {
        setCurrentTimeWindow('');
      }
    }, [onTimeRangeChange]);

    // Handle animation controls
    const handlePlayPause = useCallback(() => {
      if (!timelineRef.current) return;

      if (isAnimating) {
        timelineRef.current.pauseAnimation();
      } else {
        timelineRef.current.playAnimation();
      }
    }, [isAnimating]);

    const handleStop = useCallback(() => {
      if (!timelineRef.current) return;
      
      // Clear the tick monitoring
      if (tickCheckInterval.current) {
        clearInterval(tickCheckInterval.current);
        tickCheckInterval.current = null;
      }
      
      timelineRef.current.stopAnimation();
      timelineRef.current.setSelection(undefined);
      setCurrentTimeWindow('');
    }, []);

    const handleReset = useCallback(() => {
      if (!timelineRef.current) return;
      
      timelineRef.current.setSelection(undefined);
      setCurrentTimeWindow('');
    }, []);

    // Track last animation tick time to detect when animation ends
    const lastTickTime = useRef<number>(0);

    // Animation callbacks
    const handleAnimationPlay = useCallback((isRunning: boolean, selection?: (number | Date)[]) => {
      setIsAnimating(isRunning);
      
      if (isRunning && isLooping) {
        // Start monitoring for animation end when looping is enabled
        lastTickTime.current = Date.now();
        
        // Clear any existing interval
        if (tickCheckInterval.current) {
          clearInterval(tickCheckInterval.current);
        }
        
        // Check every 500ms if animation has stopped (no ticks for 1 second)
        tickCheckInterval.current = setInterval(() => {
          const timeSinceLastTick = Date.now() - lastTickTime.current;
          if (timeSinceLastTick > 1000 && timelineRef.current) {
            // Animation appears to have ended, restart for loop
            if (tickCheckInterval.current) {
              clearInterval(tickCheckInterval.current);
              tickCheckInterval.current = null;
            }
            // Restart animation
            timelineRef.current.playAnimation();
          }
        }, 500);
      } else if (!isRunning) {
        // Clear interval when animation stops
        if (tickCheckInterval.current) {
          clearInterval(tickCheckInterval.current);
          tickCheckInterval.current = null;
        }
      }
    }, [isLooping]);

    const handleAnimationPause = useCallback((isRunning: boolean) => {
      setIsAnimating(isRunning);
      
      // Clear the tick monitoring when paused
      if (!isRunning && tickCheckInterval.current) {
        clearInterval(tickCheckInterval.current);
        tickCheckInterval.current = null;
      }
    }, []);

    const handleAnimationTick = useCallback((selection?: (number | Date)[]) => {
      // Update last tick time for loop detection
      lastTickTime.current = Date.now();
      
      if (selection && selection.length === 2) {
        const start = selection[0] instanceof Date ? selection[0] : new Date(selection[0]);
        const end = selection[1] instanceof Date ? selection[1] : new Date(selection[1]);
        const formatDate = (date: Date) => date.toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric'
        });
        setCurrentTimeWindow(`${formatDate(start)} - ${formatDate(end)}`);
      }
    }, []);

    // Handle speed change
    const handleSpeedChange = useCallback((value: number[]) => {
      const newSpeed = value[0];
      setAnimationSpeed(newSpeed);
      // Note: We'll need to recreate the timeline with new speed
      // since animationSpeed is a prop that can't be changed dynamically
    }, []);

    // Toggle expanded state
    const toggleExpanded = useCallback(() => {
      setIsExpanded(!isExpanded);
    }, [isExpanded]);

    // Toggle visibility
    const toggleVisibility = useCallback(() => {
      const newVisibility = !isVisible;
      onVisibilityChange?.(newVisibility);
    }, [isVisible, onVisibilityChange]);

    // Expose methods via ref
    useImperativeHandle(ref, () => ({
      setSelection: (range?: [Date, Date] | [number, number]) => {
        timelineRef.current?.setSelection(range);
      },
      playAnimation: () => {
        timelineRef.current?.playAnimation();
      },
      pauseAnimation: () => {
        timelineRef.current?.pauseAnimation();
      },
      stopAnimation: () => {
        timelineRef.current?.stopAnimation();
      },
      toggleVisibility
    }), [toggleVisibility]);

    // Don't render if not visible
    if (!isVisible) {
      return null;
    }
    
    // For now, just render the timeline - the parent already checks if context is ready
    // The CosmographTimeline component will handle its own data internally

    return (
      <div className={`border-t border-border shadow-lg transition-all duration-300 ${className}`} 
           style={{ height: isExpanded ? '180px' : '80px' }}>
        
        {/* Unified Controls Bar with all actions */}
        <div className="flex items-center justify-between px-4 py-2 bg-background/80 backdrop-blur-sm border-b border-border">
          <div className="flex items-center gap-2">
            {/* Selection Counter and Actions */}
            {selectedCount > 0 && (
              <>
                <span className="text-xs bg-secondary/50 px-2 py-1 rounded">
                  {selectedCount} selected
                </span>
                <div className="flex items-center gap-1">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 w-8 p-0"
                    title="Pin Selected"
                  >
                    <Pin className="h-4 w-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 w-8 p-0"
                    title="Hide Selected"
                  >
                    <Eye className="h-4 w-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-8 w-8 p-0"
                    title="Export Selection"
                  >
                    <Download className="h-4 w-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={onClearSelection}
                    className="h-8 w-8 p-0 hover:bg-destructive/10"
                    title="Clear Selection"
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
                <div className="w-px h-5 bg-border mx-1" />
              </>
            )}

            {/* Timeline Controls */}
            <Button
              size="sm"
              variant="ghost"
              onClick={handlePlayPause}
              className="h-8 w-8 p-0"
              title={isAnimating ? "Pause animation" : "Play animation"}
            >
              {isAnimating ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </Button>

            <Button
              size="sm"
              variant="ghost"
              onClick={handleStop}
              className="h-8 w-8 p-0"
              title="Stop animation"
              disabled={!isAnimating && !selectedRange}
            >
              <RotateCcw className="h-4 w-4" />
            </Button>

            {/* Speed Control */}
            <div className="flex items-center gap-2 ml-2">
              <Clock className="h-4 w-4 text-muted-foreground" />
              <Slider
                value={[animationSpeed]}
                onValueChange={handleSpeedChange}
                min={50}
                max={1000}
                step={50}
                className="w-24"
                title={`Animation speed: ${animationSpeed}ms`}
              />
              <span className="text-xs text-muted-foreground w-12">{animationSpeed}ms</span>
            </div>

            {/* Loop Toggle */}
            <Button
              size="sm"
              variant={isLooping ? "default" : "ghost"}
              onClick={() => setIsLooping(!isLooping)}
              className="h-8 px-2"
              title="Toggle loop animation"
            >
              <SkipForward className="h-4 w-4" />
              <span className="ml-1 text-xs">Loop</span>
            </Button>

            {/* Time Window Display */}
            {currentTimeWindow && (
              <div className="ml-4 flex items-center gap-2">
                <Calendar className="h-4 w-4 text-muted-foreground" />
                <span className="text-xs text-muted-foreground">{currentTimeWindow}</span>
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* Zoom Controls */}
            <div className="flex items-center gap-1">
              <Button
                size="sm"
                variant="ghost"
                onClick={zoomOut}
                className="h-8 w-8 p-0"
                title="Zoom Out"
              >
                <ZoomOut className="h-4 w-4" />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={fitView}
                className="h-8 w-8 p-0"
                title="Fit to Screen"
              >
                <Maximize2 className="h-4 w-4" />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={zoomIn}
                className="h-8 w-8 p-0"
                title="Zoom In"
              >
                <ZoomIn className="h-4 w-4" />
              </Button>
            </div>

            <div className="w-px h-5 bg-border mx-1" />

            {/* View Controls */}
            {onScreenshot && (
              <Button
                size="sm"
                variant="ghost"
                onClick={onScreenshot}
                className="h-8 w-8 p-0"
                title="Take Screenshot"
              >
                <Camera className="h-4 w-4" />
              </Button>
            )}
            <Button
              size="sm"
              variant="ghost"
              className="h-8 w-8 p-0"
              title="Pan Mode"
            >
              <Move className="h-4 w-4" />
            </Button>

            <div className="w-px h-5 bg-border mx-1" />

            {/* Timeline Controls */}
            <Button
              size="sm"
              variant="ghost"
              onClick={handleReset}
              className="h-8 px-2"
              title="Clear timeline selection"
              disabled={!selectedRange}
            >
              <span className="text-xs">Clear</span>
            </Button>

            <Button
              size="sm"
              variant="ghost"
              onClick={toggleExpanded}
              className="h-8 w-8 p-0"
              title={isExpanded ? "Collapse timeline" : "Expand timeline"}
            >
              {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronUp className="h-4 w-4" />}
            </Button>
          </div>
        </div>

        {/* Timeline Component - Memoized to prevent re-renders */}
        <div style={{ height: isExpanded ? '120px' : '40px', padding: '0 16px' }}>
          <MemoizedTimeline
            ref={timelineRef}
            useLinksData={false}
            accessor="created_at_timestamp"
            highlightSelectedData={true}
            showAnimationControls={false}
            animationSpeed={animationSpeed}
            onSelection={handleSelection}
            onAnimationPlay={handleAnimationPlay}
            onAnimationPause={handleAnimationPause}
            onAnimationTick={handleAnimationTick}
            
            // Date formatting
            formatter={(value: number | Date) => {
              const date = value instanceof Date ? value : new Date(value);
              return date.toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric'
              });
            }}
            
            // Appearance
            padding={{ top: isExpanded ? 5 : 2, bottom: isExpanded ? 5 : 2, left: 0, right: 0 }}
            barCount={isExpanded ? 60 : 30}
            barRadius={isExpanded ? 2 : 1}
            barPadding={0.1}
            axisTickHeight={isExpanded ? 20 : 10}
            barTopMargin={isExpanded ? 20 : 5}
            
            // Custom styling with transparent background
            className={`cosmograph-timeline ${updateMode === 'instant' ? 'cosmograph-timeline-no-animation' : ''}`}
            style={{
              '--cosmograph-timeline-background': 'transparent',
              '--cosmograph-timeline-bar-color': '#4ECDC4',
              '--cosmograph-timeline-bar-opacity': '0.8',
              '--cosmograph-timeline-selection-color': '#3b82f6',
              '--cosmograph-timeline-selection-opacity': '0.3',
              '--cosmograph-timeline-axis-color': 'rgba(255, 255, 255, 0.3)',
              '--cosmograph-timeline-text-color': 'rgba(255, 255, 255, 0.6)',
              '--cosmograph-timeline-font-size': isExpanded ? '10px' : '9px',
            } as React.CSSProperties}
          />
        </div>
      </div>
    );
  }
);

GraphTimeline.displayName = 'GraphTimeline';

// Memoized CosmographTimeline wrapper to prevent re-renders on data updates
const MemoizedTimeline = memo(
  forwardRef<CosmographTimelineRef, any>((props, ref) => {
    return <CosmographTimeline {...props} ref={ref} />;
  }),
  (prevProps, nextProps) => {
    // Only re-render if these specific props change
    return (
      prevProps.animationSpeed === nextProps.animationSpeed &&
      prevProps.isExpanded === nextProps.isExpanded &&
      prevProps.accessor === nextProps.accessor &&
      prevProps.useLinksData === nextProps.useLinksData &&
      prevProps.highlightSelectedData === nextProps.highlightSelectedData &&
      prevProps.showAnimationControls === nextProps.showAnimationControls &&
      prevProps.barCount === nextProps.barCount &&
      prevProps.barRadius === nextProps.barRadius &&
      prevProps.barPadding === nextProps.barPadding &&
      prevProps.axisTickHeight === nextProps.axisTickHeight &&
      prevProps.barTopMargin === nextProps.barTopMargin
    );
  }
);

MemoizedTimeline.displayName = 'MemoizedTimeline';

export default GraphTimeline;
