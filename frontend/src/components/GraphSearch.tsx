import React, { useRef } from 'react';
import { CosmographSearch } from '@cosmograph/react';
import { Filter, Route, Focus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { GraphNode } from '../api/types';

interface GraphSearchProps {
  className?: string;
  onNodeSelect?: (node: GraphNode) => void;
  onHighlightNodes?: (nodes: GraphNode[]) => void;
  onSelectNodes?: (nodes: GraphNode[]) => void;
  onClearSelection?: () => void;
  onFilterClick?: () => void;
}

export const GraphSearch: React.FC<GraphSearchProps> = React.memo(({ 
  className = '',
  onNodeSelect,
  onHighlightNodes,
  onSelectNodes,
  onClearSelection,
  onFilterClick
}) => {
  const searchRef = useRef<any>(null);
  const lastSearchResults = useRef<GraphNode[]>([]);

  // Memoized content accessor function
  const contentAccessor = React.useCallback((node: GraphNode) => {
    if (!node.properties) return '';
    // Memoized string concatenation for better performance
    const stringValues = Object.entries(node.properties)
      .filter(([key, val]) => typeof val === 'string' && key !== 'id')
      .map(([, val]) => val);
    return stringValues.join(' ');
  }, []);

  // Memoized search accessors to prevent re-creation on every render
  const searchAccessors = React.useMemo(() => [
    {
      label: 'Label',
      accessor: (node: GraphNode) => node.label || node.id || ''
    },
    {
      label: 'Content',
      accessor: contentAccessor
    },
    {
      label: 'Type',
      accessor: (node: GraphNode) => node.node_type || ''
    },
    {
      label: 'ID',
      accessor: (node: GraphNode) => node.id || ''
    }
  ], [contentAccessor]);

  const handleSelectResult = (node: GraphNode) => {
    onNodeSelect?.(node);
  };

  const handleSearch = (nodes?: GraphNode[]) => {
    // Store search results for enter key functionality
    lastSearchResults.current = nodes || [];
    console.log(`Search found ${nodes?.length || 0} results`);
  };

  const handleEnter = (input: string | any, accessor?: any) => {
    // Handle case where input might be an object instead of string
    const inputString = typeof input === 'string' ? input : String(input);
    console.log(`Search enter: "${inputString}" using ${accessor?.label || 'default'} accessor`);
    
    // Select all nodes from the last search results (same as clicking search results)
    if (onSelectNodes && inputString.trim() && lastSearchResults.current.length > 0) {
      onSelectNodes(lastSearchResults.current);
    } else if (onHighlightNodes && inputString.trim()) {
      // Fallback to highlighting if onSelectNodes is not available
      onHighlightNodes(lastSearchResults.current);
    }
  };

  const handleAccessorSelect = (accessor: any, index: number) => {
    console.log(`Search accessor changed to: ${accessor.label}`);
  };

  // Memoized style object to prevent re-creation on every render
  const searchStyles = React.useMemo(() => ({
    '--cosmograph-search-text-color': 'hsl(var(--foreground))',
    '--cosmograph-search-input-background': 'hsl(var(--secondary) / 0.5)',
    '--cosmograph-search-input-border': '1px solid hsl(var(--border) / 0.3)',
    '--cosmograph-search-input-border-radius': '0.5rem',
    '--cosmograph-search-input-height': '2.5rem',
    '--cosmograph-search-input-padding': '0.75rem',
    '--cosmograph-search-list-background': 'hsl(var(--popover))',
    '--cosmograph-search-list-border': '1px solid hsl(var(--border))',
    '--cosmograph-search-list-border-radius': '0.5rem',
    '--cosmograph-search-list-box-shadow': '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
    '--cosmograph-search-mark-background': 'hsl(var(--primary) / 0.3)',
    '--cosmograph-search-accessor-background': 'hsl(var(--muted) / 0.5)',
    '--cosmograph-search-interactive-background': 'hsl(var(--accent))',
    '--cosmograph-search-hover-color': 'hsl(var(--accent))',
    '--cosmograph-search-focus-border': 'hsl(var(--primary) / 0.5)'
  } as React.CSSProperties), []);

  return (
    <div className={`w-full ${className}`}>
      <div className="flex items-center space-x-2">
        {/* CosmographSearch Component */}
        <div className="flex-1">
          <CosmographSearch
            ref={searchRef}
            accessors={searchAccessors}
            maxVisibleItems={8}
            limitSuggestions={50}
            minMatch={1}
            truncateValues={100}
            placeholder="Search labels, content, and types..."
            onSelectResult={handleSelectResult}
            onSearch={handleSearch}
            onEnter={handleEnter}
            onAccessorSelect={handleAccessorSelect}
            style={searchStyles}
          />
        </div>
        
        {/* Action Buttons */}
        <div className="flex items-center space-x-1 flex-shrink-0">
          <Button
            variant="ghost"
            size="sm"
            onClick={onFilterClick}
            className="h-8 px-2 hover:bg-primary/10"
            title="Filter"
          >
            <Filter className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 px-2 hover:bg-primary/10"
            title="Find Path"
          >
            <Route className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-8 px-2 hover:bg-primary/10"
            title="Focus Subgraph"
          >
            <Focus className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClearSelection}
            className="h-8 px-2 hover:bg-primary/10"
            title="Clear Selection"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}, (prevProps, nextProps) => {
  // Only re-render if essential props change (not function props)
  return prevProps.className === nextProps.className;
});