import React from 'react';
import { ChevronDown, ChevronRight, GripVertical } from 'lucide-react';
import { Button } from '@/components/ui/button';
import * as Collapsible from '@radix-ui/react-collapsible';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

export interface SectionConfig {
  id: string;
  title: string;
  isCollapsed: boolean;
  order: number;
  isVisible: boolean;
}

interface CollapsibleSectionProps {
  section: SectionConfig;
  onToggleCollapse: (id: string) => void;
  children: React.ReactNode;
  className?: string;
}

export const CollapsibleSection: React.FC<CollapsibleSectionProps> = ({
  section,
  onToggleCollapse,
  children,
  className = ""
}) => {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: section.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
  };

  if (!section.isVisible) {
    return null;
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`
        ${className} 
        ${isDragging ? 'opacity-50 z-50' : ''} 
        bg-card/30 border border-border/20 rounded-lg p-3 transition-all duration-200
      `}
    >
      <Collapsible.Root open={!section.isCollapsed}>
        <div className="flex items-center justify-between mb-2 group">
          <Collapsible.Trigger asChild>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onToggleCollapse(section.id)}
              className="flex-1 justify-start text-sm font-medium text-muted-foreground hover:text-foreground p-0 h-auto"
            >
              <div className="flex items-center gap-1">
                {section.isCollapsed ? (
                  <ChevronRight className="h-3 w-3" />
                ) : (
                  <ChevronDown className="h-3 w-3" />
                )}
                {section.title}
              </div>
            </Button>
          </Collapsible.Trigger>
          
          <div
            {...attributes}
            {...listeners}
            className="
              opacity-0 group-hover:opacity-100 transition-opacity cursor-grab active:cursor-grabbing
              p-1 hover:bg-secondary rounded text-muted-foreground hover:text-foreground
            "
            aria-label={`Drag ${section.title} section`}
          >
            <GripVertical className="h-3 w-3" />
          </div>
        </div>

        <Collapsible.Content className="CollapsibleContent overflow-hidden">
          <div className="pt-1">
            {children}
          </div>
        </Collapsible.Content>
      </Collapsible.Root>
    </div>
  );
};

// CSS for smooth collapse animations
export const collapsibleSectionStyles = `
  .CollapsibleContent {
    overflow: hidden;
  }
  .CollapsibleContent[data-state="open"] {
    animation: slideDown 200ms ease-out;
  }
  .CollapsibleContent[data-state="closed"] {
    animation: slideUp 200ms ease-out;
  }

  @keyframes slideDown {
    from {
      height: 0;
      opacity: 0;
    }
    to {
      height: var(--radix-collapsible-content-height);
      opacity: 1;
    }
  }

  @keyframes slideUp {
    from {
      height: var(--radix-collapsible-content-height);
      opacity: 1;
    }
    to {
      height: 0;
      opacity: 0;
    }
  }
`;