import React, { forwardRef, useImperativeHandle, useRef, useCallback, useEffect, useState } from 'react';
import { CosmographTimeline, useCosmograph } from '@cosmograph/react';
import type { CosmographTimelineRef } from '@cosmograph/react';
import { Play, Pause, RotateCcw, ChevronDown, ChevronUp, SkipForward, Clock, Calendar } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { logger } from '../utils/logger';

// Extend window for debugging
declare global {
  interface Window {
    timelineAccessorCount?: number;
    timelineValidDates?: number;
  }
}

interface GraphTimelineProps {
  onTimeRangeChange?: (range: [Date, Date] | [number, number] | undefined) => void;
  className?: string;
  isVisible?: boolean;
  onVisibilityChange?: (visible: boolean) => void;
}

export interface GraphTimelineHandle {
  setSelection: (range?: [Date, Date] | [number, number]) => void;
  playAnimation: () => void;
  pauseAnimation: () => void;
  stopAnimation: () => void;
  toggleVisibility: () => void;
}

export const GraphTimeline = forwardRef<GraphTimelineHandle, GraphTimelineProps>(
  ({ onTimeRangeChange, className = '', isVisible = true, onVisibilityChange }, ref) => {
    const timelineRef = useRef<CosmographTimelineRef>(null);
    const cosmograph = useCosmograph();
    const [isAnimating, setIsAnimating] = useState(false);
    const [selectedRange, setSelectedRange] = useState<[Date, Date] | [number, number] | undefined>();
    const [hasTemporalData, setHasTemporalData] = useState(false);
    const [isExpanded, setIsExpanded] = useState(true);
    const [animationSpeed, setAnimationSpeed] = useState(200);
    const [isLooping, setIsLooping] = useState(false);
    const [currentTimeWindow, setCurrentTimeWindow] = useState<string>('');

    // Show timeline when component mounts
    useEffect(() => {
      setHasTemporalData(true);
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
        
        logger.log('Timeline: Range selected', {
          start: selection[0],
          end: selection[1],
          isManual
        });
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
      
      timelineRef.current.stopAnimation();
      timelineRef.current.setSelection(undefined);
      setCurrentTimeWindow('');
    }, []);

    const handleReset = useCallback(() => {
      if (!timelineRef.current) return;
      
      timelineRef.current.setSelection(undefined);
      setCurrentTimeWindow('');
    }, []);

    // Animation callbacks
    const handleAnimationPlay = useCallback((isRunning: boolean, selection?: (number | Date)[]) => {
      setIsAnimating(isRunning);
      if (isLooping && !isRunning && selection) {
        // Restart animation if looping is enabled
        setTimeout(() => {
          timelineRef.current?.playAnimation();
        }, 100);
      }
    }, [isLooping]);

    const handleAnimationPause = useCallback((isRunning: boolean) => {
      setIsAnimating(isRunning);
    }, []);

    const handleAnimationTick = useCallback((selection?: (number | Date)[]) => {
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

    if (!hasTemporalData || !isVisible) {
      return null;
    }

    return (
      <div className={`border-t border-border shadow-lg transition-all duration-300 ${className}`} 
           style={{ height: isExpanded ? '180px' : '120px' }}>
        
        {/* Controls Bar */}
        <div className="flex items-center justify-between px-4 py-2 bg-background/80 backdrop-blur-sm border-b border-border">
          <div className="flex items-center gap-2">
            {/* Play/Pause Button */}
            <Button
              size="sm"
              variant="ghost"
              onClick={handlePlayPause}
              className="h-8 w-8 p-0"
              title={isAnimating ? "Pause animation" : "Play animation"}
            >
              {isAnimating ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </Button>

            {/* Stop Button */}
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
            {/* Reset Selection */}
            <Button
              size="sm"
              variant="ghost"
              onClick={handleReset}
              className="h-8 px-2"
              title="Clear selection"
              disabled={!selectedRange}
            >
              <span className="text-xs">Clear</span>
            </Button>

            {/* Expand/Collapse Button */}
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

        {/* Timeline Component */}
        <div style={{ height: isExpanded ? '120px' : '60px', padding: '0 16px' }}>
          <CosmographTimeline
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
            padding={{ top: 5, bottom: 5, left: 0, right: 0 }}
            barCount={isExpanded ? 60 : 40}
            barRadius={2}
            barPadding={0.1}
            axisTickHeight={isExpanded ? 20 : 15}
            barTopMargin={isExpanded ? 20 : 10}
            
            // Custom styling with transparent background
            className="cosmograph-timeline"
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