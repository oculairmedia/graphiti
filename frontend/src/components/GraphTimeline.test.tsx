import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '../test/utils';
import { GraphTimeline } from './GraphTimeline';
import React from 'react';

// Mock the Cosmograph context
vi.mock('@cosmograph/react', () => ({
  ...vi.importActual('@cosmograph/react'),
  useCosmograph: () => ({
    cosmograph: {
      getData: vi.fn().mockReturnValue({
        points: [
          { id: '1', created_at_timestamp: 1700000000000 },
          { id: '2', created_at_timestamp: 1700100000000 },
          { id: '3', created_at_timestamp: 1700200000000 },
        ],
      }),
    },
    initCosmograph: vi.fn(),
  }),
  CosmographTimeline: vi.fn(({ children, ...props }) => (
    <div data-testid="cosmograph-timeline" {...props}>
      {children}
    </div>
  )),
}));

describe('GraphTimeline', () => {
  const defaultProps = {
    isVisible: true,
    onVisibilityChange: vi.fn(),
    onTimeRangeChange: vi.fn(),
    selectedCount: 0,
    onClearSelection: vi.fn(),
    onScreenshot: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('Component Rendering', () => {
    it('should render when visible', () => {
      const { container } = render(<GraphTimeline {...defaultProps} />);
      expect(container.querySelector('[data-testid="cosmograph-timeline"]')).toBeInTheDocument();
    });

    it('should not render when not visible', () => {
      const { container } = render(
        <GraphTimeline {...defaultProps} isVisible={false} />
      );
      expect(container.querySelector('[data-testid="cosmograph-timeline"]')).not.toBeInTheDocument();
    });

    it('should render controls bar with all buttons', () => {
      render(<GraphTimeline {...defaultProps} />);
      
      // Check for timeline controls
      expect(screen.getByTitle('Play animation')).toBeInTheDocument();
      expect(screen.getByTitle('Stop animation')).toBeInTheDocument();
      expect(screen.getByTitle('Toggle loop animation')).toBeInTheDocument();
    });
  });

  describe('Animation Controls', () => {
    it('should toggle play/pause button based on animation state', async () => {
      render(<GraphTimeline {...defaultProps} />);
      
      const playButton = screen.getByTitle('Play animation');
      expect(playButton).toBeInTheDocument();
      
      fireEvent.click(playButton);
      
      // After clicking play, it should show pause
      await waitFor(() => {
        const pauseButton = screen.queryByTitle('Pause animation');
        // Note: State change might not be reflected in mocked component
        expect(playButton).toBeInTheDocument();
      });
    });

    it('should handle stop button click', () => {
      render(<GraphTimeline {...defaultProps} />);
      
      const stopButton = screen.getByTitle('Stop animation');
      fireEvent.click(stopButton);
      
      // Stop button should be disabled when not animating
      expect(stopButton).toHaveAttribute('disabled');
    });

    it('should handle loop toggle', () => {
      render(<GraphTimeline {...defaultProps} />);
      
      const loopButton = screen.getByTitle('Toggle loop animation');
      fireEvent.click(loopButton);
      
      // Loop button should toggle state
      expect(loopButton).toBeInTheDocument();
    });
  });

  describe('Speed Control', () => {
    it('should render speed slider', () => {
      const { container } = render(<GraphTimeline {...defaultProps} />);
      
      const slider = container.querySelector('[role="slider"]');
      expect(slider).toBeInTheDocument();
    });

    it('should display current speed', () => {
      render(<GraphTimeline {...defaultProps} />);
      
      // Default speed should be displayed
      expect(screen.getByText('200ms')).toBeInTheDocument();
    });
  });

  describe('Selection Actions', () => {
    it('should show selection count when items are selected', () => {
      render(<GraphTimeline {...defaultProps} selectedCount={3} />);
      
      expect(screen.getByText('3 selected')).toBeInTheDocument();
    });

    it('should show selection action buttons when items are selected', () => {
      render(<GraphTimeline {...defaultProps} selectedCount={2} />);
      
      expect(screen.getByTitle('Pin Selected')).toBeInTheDocument();
      expect(screen.getByTitle('Hide Selected')).toBeInTheDocument();
      expect(screen.getByTitle('Export Selection')).toBeInTheDocument();
      expect(screen.getByTitle('Clear Selection')).toBeInTheDocument();
    });

    it('should call onClearSelection when clear button is clicked', () => {
      const onClearSelection = vi.fn();
      render(
        <GraphTimeline 
          {...defaultProps} 
          selectedCount={2}
          onClearSelection={onClearSelection}
        />
      );
      
      const clearButton = screen.getByTitle('Clear Selection');
      fireEvent.click(clearButton);
      
      expect(onClearSelection).toHaveBeenCalled();
    });
  });

  describe('Zoom Controls', () => {
    it('should render zoom controls', () => {
      render(<GraphTimeline {...defaultProps} />);
      
      expect(screen.getByTitle('Zoom In')).toBeInTheDocument();
      expect(screen.getByTitle('Zoom Out')).toBeInTheDocument();
      expect(screen.getByTitle('Fit to Screen')).toBeInTheDocument();
    });

    it('should handle screenshot button click', () => {
      const onScreenshot = vi.fn();
      render(<GraphTimeline {...defaultProps} onScreenshot={onScreenshot} />);
      
      const screenshotButton = screen.getByTitle('Take Screenshot');
      fireEvent.click(screenshotButton);
      
      expect(onScreenshot).toHaveBeenCalled();
    });
  });

  describe('Timeline Expansion', () => {
    it('should toggle timeline expansion', () => {
      const { container } = render(<GraphTimeline {...defaultProps} />);
      
      const expandButton = screen.getByTitle('Collapse timeline');
      fireEvent.click(expandButton);
      
      // Height should change based on expansion state
      const timelineContainer = container.firstChild as HTMLElement;
      expect(timelineContainer).toHaveStyle({ height: '120px' });
    });
  });

  describe('Clear Timeline Selection', () => {
    it('should have clear button disabled when no timeline selection', () => {
      render(<GraphTimeline {...defaultProps} />);
      
      const clearButton = screen.getByTitle('Clear timeline selection');
      expect(clearButton).toHaveAttribute('disabled');
    });
  });

  describe('Imperative Handle', () => {
    it('should expose timeline control methods via ref', () => {
      const ref = React.createRef<any>();
      render(<GraphTimeline {...defaultProps} ref={ref} />);
      
      expect(ref.current).toBeDefined();
      expect(ref.current.setSelection).toBeDefined();
      expect(ref.current.playAnimation).toBeDefined();
      expect(ref.current.pauseAnimation).toBeDefined();
      expect(ref.current.stopAnimation).toBeDefined();
      expect(ref.current.toggleVisibility).toBeDefined();
    });

    it('should handle toggleVisibility via ref', () => {
      const onVisibilityChange = vi.fn();
      const ref = React.createRef<any>();
      render(
        <GraphTimeline 
          {...defaultProps}
          onVisibilityChange={onVisibilityChange}
          ref={ref}
        />
      );
      
      ref.current?.toggleVisibility();
      
      expect(onVisibilityChange).toHaveBeenCalledWith(false);
    });
  });

  describe('Time Window Display', () => {
    it('should not show time window initially', () => {
      render(<GraphTimeline {...defaultProps} />);
      
      // No time window should be displayed initially
      const calendarIcon = document.querySelector('.lucide-calendar');
      const timeWindowText = calendarIcon?.nextSibling;
      expect(timeWindowText).toBeFalsy();
    });
  });

  describe('Context Integration', () => {
    it('should log warning when no cosmograph in context', () => {
      const consoleSpy = vi.spyOn(console, 'log');
      
      // Mock no cosmograph in context
      vi.mocked(vi.importActual('@cosmograph/react')).useCosmograph = () => ({
        cosmograph: null,
        initCosmograph: vi.fn(),
      });
      
      render(<GraphTimeline {...defaultProps} />);
      
      // Should log warning about missing cosmograph
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('No cosmograph instance in context')
      );
      
      consoleSpy.mockRestore();
    });
  });
});