import React, { useState } from 'react';
import { Square, Hexagon, MousePointer, Link2, Move } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

export type SelectionMode = 'normal' | 'rectangle' | 'polygon' | 'connected';

interface SelectionToolsProps {
  onModeChange: (mode: SelectionMode) => void;
  className?: string;
}

export const SelectionTools: React.FC<SelectionToolsProps> = ({ onModeChange, className }) => {
  const [activeMode, setActiveMode] = useState<SelectionMode>('normal');

  const handleModeChange = (mode: SelectionMode) => {
    setActiveMode(mode);
    onModeChange(mode);
  };

  return (
    <TooltipProvider>
      <div className={`flex items-center space-x-1 ${className}`}>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant={activeMode === 'normal' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => handleModeChange('normal')}
              className="h-8 px-2"
              title="Normal Selection"
            >
              <MousePointer className="h-3 w-3" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>Normal Selection</p>
            <p className="text-xs text-muted-foreground">Click to select individual nodes</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant={activeMode === 'rectangle' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => handleModeChange('rectangle')}
              className="h-8 px-2"
              title="Rectangle Selection"
            >
              <Square className="h-3 w-3" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>Rectangle Selection</p>
            <p className="text-xs text-muted-foreground">Draw a rectangle to select multiple nodes</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant={activeMode === 'polygon' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => handleModeChange('polygon')}
              className="h-8 px-2"
              title="Polygon Selection"
            >
              <Hexagon className="h-3 w-3" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>Polygon Selection</p>
            <p className="text-xs text-muted-foreground">Draw a custom shape to select nodes</p>
          </TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              variant={activeMode === 'connected' ? 'default' : 'ghost'}
              size="sm"
              onClick={() => handleModeChange('connected')}
              className="h-8 px-2"
              title="Connected Nodes"
            >
              <Link2 className="h-3 w-3" />
            </Button>
          </TooltipTrigger>
          <TooltipContent>
            <p>Connected Nodes Selection</p>
            <p className="text-xs text-muted-foreground">Click a node to select all connected nodes</p>
          </TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  );
};