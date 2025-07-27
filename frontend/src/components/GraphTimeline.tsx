import React, { forwardRef, useImperativeHandle, useRef, useCallback, useEffect, useState } from 'react';
import { CosmographTimeline, useCosmograph } from '@cosmograph/react';
import type { CosmographTimelineRef } from '@cosmograph/react';
import { Calendar, Play, Pause, RotateCcw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { GraphNode, GraphEdge } from '../api/types';
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
}

export interface GraphTimelineHandle {
  setSelection: (range?: [Date, Date] | [number, number]) => void;
  playAnimation: () => void;
  pauseAnimation: () => void;
  stopAnimation: () => void;
}

export const GraphTimeline = forwardRef<GraphTimelineHandle, GraphTimelineProps>(
  ({ onTimeRangeChange, className = '' }, ref) => {
    const timelineRef = useRef<CosmographTimelineRef>(null);
    const cosmograph = useCosmograph();
    const [isAnimating, setIsAnimating] = useState(false);
    const [selectedRange, setSelectedRange] = useState<[Date, Date] | [number, number] | undefined>();
    const [hasTemporalData, setHasTemporalData] = useState(false);

    // Show timeline when component mounts
    useEffect(() => {
      setHasTemporalData(true);
    }, []);

    // Handle timeline selection
    const handleSelection = useCallback((selection?: [number, number] | [Date, Date], isManual?: boolean) => {
      setSelectedRange(selection);
      onTimeRangeChange?.(selection);
      
      if (selection) {
        logger.log('Timeline: Range selected', {
          start: selection[0],
          end: selection[1],
          isManual
        });
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

    const handleReset = useCallback(() => {
      if (!timelineRef.current) return;
      
      timelineRef.current.stopAnimation();
      timelineRef.current.setSelection(undefined);
    }, []);

    // Animation callbacks
    const handleAnimationPlay = useCallback((isRunning: boolean) => {
      setIsAnimating(isRunning);
    }, []);

    const handleAnimationPause = useCallback((isRunning: boolean) => {
      setIsAnimating(isRunning);
    }, []);

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
      }
    }), []);

    if (!hasTemporalData) {
      return null;
    }

    return (
      <div className={`border-t border-border shadow-lg ${className}`} style={{ height: '120px', padding: '0 16px' }}>
        <CosmographTimeline
          ref={timelineRef}
          useLinksData={false}
          accessor="created_at_timestamp"
          highlightSelectedData={true}
          showAnimationControls={false}
          animationSpeed={200}
          onSelection={handleSelection}
          onAnimationPlay={handleAnimationPlay}
          onAnimationPause={handleAnimationPause}
          
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
          barCount={60}
          barRadius={2}
          barPadding={0.1}
          axisTickHeight={20}
          
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
            '--cosmograph-timeline-font-size': '10px',
          } as React.CSSProperties}
        />
      </div>
    );
  }
);

GraphTimeline.displayName = 'GraphTimeline';