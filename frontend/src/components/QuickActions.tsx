import React from 'react';
import { Maximize2, ZoomIn, ZoomOut, Camera, Trash2, Pin, Eye, Download, Move } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

interface QuickActionsProps {
  selectedCount: number;
  onClearSelection: () => void;
  onFitToScreen: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onScreenshot: () => void;
}

export const QuickActions: React.FC<QuickActionsProps> = ({
  selectedCount,
  onClearSelection,
  onFitToScreen,
  onZoomIn,
  onZoomOut,
  onScreenshot
}) => {
  const handleZoomIn = () => {
    console.log('QuickActions: Zoom In clicked');
    onZoomIn();
  };

  const handleZoomOut = () => {
    console.log('QuickActions: Zoom Out clicked');
    onZoomOut();
  };

  const handleFitToScreen = () => {
    console.log('QuickActions: Fit to Screen clicked');
    onFitToScreen();
  };

  return (
    <div className="glass-panel rounded-full px-4 py-2 flex items-center space-x-2 animate-fade-in">
      
      {/* Selection Counter */}
      {selectedCount > 0 && (
        <>
          <Badge variant="secondary" className="text-xs">
            {selectedCount} selected
          </Badge>
          
          {/* Bulk Actions */}
          <div className="flex items-center space-x-1 border-l border-border/30 pl-2">
            <Button
              variant="ghost"
              size="sm"
              className="h-8 px-2 hover:bg-primary/10"
              title="Pin Selected"
            >
              <Pin className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 px-2 hover:bg-primary/10"
              title="Hide Selected"
            >
              <Eye className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 px-2 hover:bg-primary/10"
              title="Export Selection"
            >
              <Download className="h-3 w-3" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={onClearSelection}
              className="h-8 px-2 hover:bg-destructive/10 text-destructive"
              title="Clear Selection"
            >
              <Trash2 className="h-3 w-3" />
            </Button>
          </div>
        </>
      )}

      {/* View Controls */}
      <div className={`flex items-center space-x-1 ${selectedCount > 0 ? 'border-l border-border/30 pl-2' : ''}`}>
        <Button
          variant="ghost"
          size="sm"
          onClick={onScreenshot}
          className="h-8 px-2 hover:bg-primary/10"
          title="Take Screenshot"
        >
          <Camera className="h-3 w-3" />
        </Button>
      </div>

      {/* Zoom Controls */}
      <div className="flex items-center space-x-1 border-l border-border/30 pl-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={handleZoomOut}
          className="h-8 px-2 hover:bg-primary/10"
          title="Zoom Out"
        >
          <ZoomOut className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleFitToScreen}
          className="h-8 px-2 hover:bg-primary/10"
          title="Fit to Screen"
        >
          <Maximize2 className="h-3 w-3" />
        </Button>
        <Button
          variant="ghost"
          size="sm"
          onClick={handleZoomIn}
          className="h-8 px-2 hover:bg-primary/10"
          title="Zoom In"
        >
          <ZoomIn className="h-3 w-3" />
        </Button>
      </div>

      {/* Graph Navigation */}
      <div className="flex items-center space-x-1 border-l border-border/30 pl-2">
        <Button
          variant="ghost"
          size="sm"
          className="h-8 px-2 hover:bg-primary/10"
          title="Pan Mode"
        >
          <Move className="h-3 w-3" />
        </Button>
      </div>
    </div>
  );
};