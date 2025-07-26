import React, { useRef, useEffect, useState, useCallback } from 'react';
import { Filter, Route, Focus, Trash2, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useGraphConfig } from '@/contexts/GraphConfigContext';
import { GraphNode } from '../api/types';

interface GraphSearchProps {
  className?: string;
  onNodeSelect?: (node: GraphNode) => void;
  onHighlightNodes?: (nodes: GraphNode[]) => void;
  onSelectNodes?: (nodes: GraphNode[]) => void;
  onClearSelection?: () => void;
  onFilterClick?: () => void;
  nodes?: GraphNode[]; // Current graph nodes for search
}

export const GraphSearch: React.FC<GraphSearchProps> = React.memo(({ 
  className = '',
  onNodeSelect,
  onHighlightNodes,
  onSelectNodes,
  onClearSelection,
  onFilterClick,
  nodes = []
}) => {
  // Get cosmographRef and node type colors from context
  const { cosmographRef, config } = useGraphConfig();
  
  // Search state management
  const [searchValue, setSearchValue] = useState('');
  const [searchResults, setSearchResults] = useState<GraphNode[]>([]);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);
  const [visibleResultsCount, setVisibleResultsCount] = useState(20); // Start with 20 visible results
  
  // Refs for DOM elements
  const searchContainerRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const resultsListRef = useRef<HTMLDivElement>(null);
  
  // Real-time search function that works with current nodes
  const performSearch = useCallback((query: string) => {
    if (!query.trim()) {
      setSearchResults([]);
      setIsSearchOpen(false);
      return;
    }
    
    const lowercaseQuery = query.toLowerCase();
    const results = nodes.filter(node => {
      const label = (node.label || node.id || '').toLowerCase();
      const type = (node.node_type || '').toLowerCase();
      const id = (node.id || '').toLowerCase();
      
      // Search in properties as well
      let propertiesMatch = false;
      if (node.properties) {
        const propertiesText = Object.values(node.properties)
          .filter(val => typeof val === 'string')
          .join(' ')
          .toLowerCase();
        propertiesMatch = propertiesText.includes(lowercaseQuery);
      }
      
      return label.includes(lowercaseQuery) || 
             type.includes(lowercaseQuery) || 
             id.includes(lowercaseQuery) ||
             propertiesMatch;
    }); // Return all matching results
    
    // Sort results by relevance - exact matches first
    results.sort((a, b) => {
      const aLabel = (a.label || a.id).toLowerCase();
      const bLabel = (b.label || b.id).toLowerCase();
      
      const aExact = aLabel === lowercaseQuery ? 1 : 0;
      const bExact = bLabel === lowercaseQuery ? 1 : 0;
      
      if (aExact !== bExact) return bExact - aExact;
      
      const aStarts = aLabel.startsWith(lowercaseQuery) ? 1 : 0;
      const bStarts = bLabel.startsWith(lowercaseQuery) ? 1 : 0;
      
      return bStarts - aStarts;
    });
    
    setSearchResults(results);
    setIsSearchOpen(results.length > 0);
    setActiveIndex(-1);
    setVisibleResultsCount(20); // Reset visible count on new search
    
    console.log(`🔍 Search "${query}" found ${results.length} results`);
  }, [nodes]);
  
  // Handle search input changes
  const handleSearchChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setSearchValue(value);
    performSearch(value);
  }, [performSearch]);
  
  // Handle scroll to load more results
  const handleResultsScroll = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    const target = e.target as HTMLDivElement;
    const { scrollTop, scrollHeight, clientHeight } = target;
    
    // If scrolled near bottom (90%) and we have more results to show
    if (scrollTop + clientHeight >= scrollHeight * 0.9 && visibleResultsCount < searchResults.length) {
      setVisibleResultsCount(prev => Math.min(prev + 20, searchResults.length));
    }
  }, [visibleResultsCount, searchResults.length]);

  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!isSearchOpen) return;
    
    const visibleResults = searchResults.slice(0, visibleResultsCount);
    
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setActiveIndex(prev => Math.min(prev + 1, visibleResults.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setActiveIndex(prev => Math.max(prev - 1, -1));
        break;
      case 'Enter':
        e.preventDefault();
        if (activeIndex >= 0 && searchResults[activeIndex]) {
          handleSelectResult(searchResults[activeIndex]);
        } else if (searchResults.length > 0) {
          // Select all results if no specific item is active
          if (onSelectNodes) {
            onSelectNodes(searchResults);
            console.log(`🎯 Selected all ${searchResults.length} search results`);
          }
        }
        break;
      case 'Escape':
        setIsSearchOpen(false);
        setActiveIndex(-1);
        searchInputRef.current?.blur();
        break;
    }
  }, [isSearchOpen, searchResults, activeIndex, onSelectNodes, visibleResultsCount]);
  
  // Handle result selection
  const handleSelectResult = useCallback((node: GraphNode) => {
    console.log('🎯 Search result selected:', node.label || node.id);
    
    // Call the node selection handler
    if (onNodeSelect) {
      onNodeSelect(node);
    }
    
    // Focus and select the node in Cosmograph if available
    if (cosmographRef?.current) {
      try {
        // Find the node index in the current data
        const nodeIndex = nodes.findIndex(n => n.id === node.id);
        if (nodeIndex >= 0) {
          // Use Cosmograph's focus methods
          if (typeof cosmographRef.current.setFocusedPoint === 'function') {
            cosmographRef.current.setFocusedPoint(nodeIndex);
            console.log(`🎯 Focused Cosmograph node at index ${nodeIndex}`);
          }
          
          // Also select the node
          if (typeof cosmographRef.current.selectPoint === 'function') {
            cosmographRef.current.selectPoint(nodeIndex);
            console.log(`✅ Selected Cosmograph node at index ${nodeIndex}`);
          } else if (typeof cosmographRef.current.selectPoints === 'function') {
            cosmographRef.current.selectPoints([nodeIndex]);
            console.log(`✅ Selected Cosmograph node at index ${nodeIndex}`);
          }
        }
      } catch (error) {
        console.warn('Could not focus/select node in Cosmograph:', error);
      }
    }
    
    // Clear search
    setSearchValue('');
    setIsSearchOpen(false);
    setActiveIndex(-1);
  }, [onNodeSelect, cosmographRef, nodes]);
  
  // Close search results when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(event.target as Node)) {
        setIsSearchOpen(false);
        setActiveIndex(-1);
      }
    };
    
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);
  
  // Convert hex color to HSL for CSS custom properties
  const hexToHsl = useCallback((hex: string) => {
    // Remove # if present
    hex = hex.replace('#', '');
    
    // Parse hex values
    const r = parseInt(hex.substr(0, 2), 16) / 255;
    const g = parseInt(hex.substr(2, 2), 16) / 255;
    const b = parseInt(hex.substr(4, 2), 16) / 255;

    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    let h = 0;
    let s = 0;
    const l = (max + min) / 2;

    if (max !== min) {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      switch (max) {
        case r: h = (g - b) / d + (g < b ? 6 : 0); break;
        case g: h = (b - r) / d + 2; break;
        case b: h = (r - g) / d + 4; break;
      }
      h /= 6;
    }

    return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
  }, []);

  // Get HSL color for badge styling
  const getBadgeHslColor = useCallback((nodeType: string) => {
    const hexColor = config.nodeTypeColors[nodeType];
    return hexColor ? hexToHsl(hexColor) : null;
  }, [config.nodeTypeColors, hexToHsl]);

  // Log when nodes data changes
  useEffect(() => {
    console.log('🔍 GraphSearch received nodes:', {
      count: nodes.length,
      firstNode: nodes[0],
      nodeTypes: [...new Set(nodes.map(n => n.node_type).filter(Boolean))].slice(0, 5)
    });
  }, [nodes]);
  
  return (
    <div className={`w-full ${className}`}>
      <div className="flex items-center space-x-2">
        {/* Search Input Container */}
        <div className="flex-1 relative" ref={searchContainerRef}>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              ref={searchInputRef}
              type="text"
              value={searchValue}
              onChange={handleSearchChange}
              onKeyDown={handleKeyDown}
              placeholder="Search nodes by name, type, ID, or properties..."
              className="pl-10 h-10 bg-secondary/50 border-border/30 focus:border-primary/50 transition-colors"
            />
            {searchValue && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setSearchValue('');
                  setSearchResults([]);
                  setIsSearchOpen(false);
                }}
                className="absolute right-1 top-1/2 -translate-y-1/2 h-8 w-8 p-0 hover:bg-secondary"
              >
                ×
              </Button>
            )}
          </div>
          
          {/* Search Results Dropdown */}
          {isSearchOpen && searchResults.length > 0 && (
            <div 
              ref={resultsListRef}
              className="absolute top-full left-0 right-0 mt-1 bg-popover border border-border/30 rounded-md shadow-lg z-50 max-h-80 overflow-y-auto custom-scrollbar"
              onScroll={handleResultsScroll}
            >
              <div className="pb-12">
                {searchResults.slice(0, visibleResultsCount).map((node, index) => (
                <div
                  key={node.id}
                  onClick={() => handleSelectResult(node)}
                  className={`px-3 py-2 cursor-pointer border-b border-border/20 last:border-b-0 transition-colors ${
                    index === activeIndex ? 'bg-accent' : 'hover:bg-accent/50'
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      {/* Node name with highlighting */}
                      <div className="font-medium text-sm truncate">
                        {(() => {
                          const label = node.label || node.id;
                          const lowercaseLabel = label.toLowerCase();
                          const lowercaseQuery = searchValue.toLowerCase();
                          
                          if (lowercaseLabel.includes(lowercaseQuery)) {
                            const parts = label.split(new RegExp(`(${searchValue})`, 'gi'));
                            return parts.map((part, i) => (
                              part.toLowerCase() === lowercaseQuery ? 
                                <mark key={i} className="bg-primary/30">{part}</mark> : part
                            ));
                          }
                          return label;
                        })()}
                      </div>
                      
                      {/* Compact content preview */}
                      <div className="text-xs text-muted-foreground truncate">
                        {(() => {
                          // Get content from properties
                          const content = node.properties?.content || node.properties?.description || node.properties?.summary;
                          if (content && typeof content === 'string') {
                            return content.length > 60 ? `${content.substring(0, 60)}...` : content;
                          }
                          return `ID: ${node.id.substring(0, 12)}...`;
                        })()}
                      </div>
                    </div>
                    
                    {/* Node type badge with dynamic color via CSS custom properties */}
                    {node.node_type && (
                      <div className="flex-shrink-0">
                        <span 
                          className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                            getBadgeHslColor(node.node_type) ? 'search-badge' : 'search-badge-default'
                          }`}
                          style={getBadgeHslColor(node.node_type) ? {
                            '--badge-color': getBadgeHslColor(node.node_type)
                          } as React.CSSProperties : undefined}
                        >
                          {node.node_type}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
                
                {/* Load More Indicator */}
                {visibleResultsCount < searchResults.length && (
                  <div className="px-4 py-2 text-center text-xs text-muted-foreground bg-muted/20 border-t border-border/20">
                    Showing {visibleResultsCount} of {searchResults.length} results. Scroll for more...
                  </div>
                )}
              </div>
              
              {/* Search Actions Footer - Always visible */}
              <div className="px-4 py-2 bg-popover/95 backdrop-blur-sm border-t border-border/20 sticky bottom-0">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{searchResults.length} result{searchResults.length !== 1 ? 's' : ''} found</span>
                  <div className="flex space-x-4">
                    <span>↑↓ Navigate</span>
                    <span>Enter: Select{searchResults.length > 1 ? ' all' : ''}</span>
                    <span>Esc: Close</span>
                  </div>
                </div>
              </div>
            </div>
          )}
          
          {/* No Results Message */}
          {isSearchOpen && searchResults.length === 0 && searchValue.trim() && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-popover border border-border/30 rounded-md shadow-lg z-50">
              <div className="px-4 py-3 text-center text-sm text-muted-foreground">
                No nodes found matching "{searchValue}"
              </div>
            </div>
          )}
        </div>
        
        {/* Action Buttons */}
        <div className="flex items-center space-x-1 flex-shrink-0">
          <Button
            variant="ghost"
            size="sm"
            onClick={onFilterClick}
            className="h-10 px-3 hover:bg-primary/10"
            title="Filter"
          >
            <Filter className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-10 px-3 hover:bg-primary/10"
            title="Find Path"
          >
            <Route className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-10 px-3 hover:bg-primary/10"
            title="Focus Subgraph"
          >
            <Focus className="h-4 w-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClearSelection}
            className="h-10 px-3 hover:bg-primary/10"
            title="Clear Selection"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}, (prevProps, nextProps) => {
  // Only re-render if essential props change
  return (
    prevProps.className === nextProps.className &&
    prevProps.nodes === nextProps.nodes
  );
});

GraphSearch.displayName = 'GraphSearch';