import React, { useRef, useState, useCallback, useEffect } from 'react';
import { Search, X, AlertCircle, Loader2, ChevronRight, Calendar, Tag } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { cn } from '@/lib/utils';
import { useGraphitiSearch } from '@/hooks/useGraphitiSearch';
import type { GraphCanvasRef } from '@/components/GraphCanvas';
import type { NodeResult } from '@/api/types';

interface GraphitiSearchProps {
  graphCanvasRef?: React.RefObject<GraphCanvasRef>;
  className?: string;
  onNodeSelect?: (node: NodeResult) => void;
}

export const GraphitiSearch: React.FC<GraphitiSearchProps> = ({
  graphCanvasRef,
  className,
  onNodeSelect,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [displayedResults, setDisplayedResults] = useState(10); // Start with 10 results
  const inputRef = useRef<HTMLInputElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const {
    searchQuery,
    setSearchQuery,
    searchResults,
    isSearching,
    searchError,
    selectedNodeId,
    selectNode,
    clearHighlights,
  } = useGraphitiSearch({
    graphCanvasRef,
    onNodeSelect: (node) => {
      onNodeSelect?.(node);
      setIsExpanded(false);
    },
  });

  const handleClear = () => {
    setSearchQuery('');
    clearHighlights();
    inputRef.current?.focus();
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { 
      month: 'short', 
      day: 'numeric', 
      year: 'numeric' 
    });
  };

  const getCentralityScore = (node: NodeResult) => {
    const attrs = node.attributes;
    const pagerank = attrs.pagerank_centrality || 0;
    const degree = attrs.degree_centrality || 0;
    return Math.max(pagerank * 100, degree * 100);
  };

  // Handle infinite scroll
  const handleScroll = useCallback(() => {
    if (!scrollRef.current) return;
    
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    if (scrollTop + clientHeight >= scrollHeight - 50) { // Load more when near bottom
      if (displayedResults < searchResults.length) {
        setDisplayedResults(prev => Math.min(prev + 10, searchResults.length));
      }
    }
  }, [displayedResults, searchResults.length]);

  // Reset displayed results when search results change
  useEffect(() => {
    setDisplayedResults(10);
  }, [searchResults]);

  return (
    <div className={cn('space-y-3', className)}>
      {/* Search Input */}
      <div className="relative">
        <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          ref={inputRef}
          type="text"
          placeholder="Search entities, concepts, or relationships..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onFocus={() => setIsExpanded(true)}
          className="pl-8 pr-10"
        />
        {searchQuery && (
          <Button
            variant="ghost"
            size="sm"
            className="absolute right-1 top-1 h-7 w-7 p-0"
            onClick={handleClear}
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>

      {/* Search Results */}
      {isExpanded && searchQuery && (
        <div className="space-y-2">
          {isSearching && (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          )}

          {searchError && (
            <Alert variant="destructive">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                {searchError instanceof Error ? searchError.message : 'Search failed'}
              </AlertDescription>
            </Alert>
          )}

          {!isSearching && !searchError && searchResults.length === 0 && (
            <div className="text-center py-4 text-sm text-muted-foreground">
              No results found for "{searchQuery}"
            </div>
          )}

          {searchResults.length > 0 && (
            <>
              <ScrollArea className="h-[400px]" ref={scrollRef} onScrollCapture={handleScroll}>
                <div className="space-y-2 pr-4">
                  {searchResults.slice(0, displayedResults).map((node) => (
                    <Card
                      key={node.uuid}
                      className={cn(
                        'cursor-pointer transition-all hover:shadow-md',
                        selectedNodeId === node.uuid && 'ring-2 ring-primary'
                      )}
                      onClick={() => selectNode(node)}
                    >
                      <CardContent className="p-3 space-y-2">
                        {/* Node Name and Type */}
                        <div className="flex items-start justify-between gap-2">
                          <h4 className="font-medium text-sm line-clamp-1 flex-1">
                            {node.name}
                          </h4>
                          <Badge variant="secondary" className="text-xs shrink-0">
                            {node.labels[0] || 'Entity'}
                          </Badge>
                        </div>

                        {/* Summary */}
                        {node.summary && (
                          <p className="text-xs text-muted-foreground line-clamp-2">
                            {node.summary}
                          </p>
                        )}

                        {/* Metadata */}
                        <div className="flex items-center gap-3 text-xs text-muted-foreground">
                          <div className="flex items-center gap-1">
                            <Calendar className="h-3 w-3" />
                            <span>{formatDate(node.created_at)}</span>
                          </div>
                          {node.group_id && (
                            <div className="flex items-center gap-1">
                              <Tag className="h-3 w-3" />
                              <span className="truncate max-w-[100px]">{node.group_id}</span>
                            </div>
                          )}
                          {getCentralityScore(node) > 1 && (
                            <Badge variant="outline" className="text-xs px-1 py-0">
                              {getCentralityScore(node).toFixed(0)}% central
                            </Badge>
                          )}
                        </div>

                        {/* Click to Focus */}
                        <div className="flex items-center justify-end text-xs text-primary">
                          <span>Click to focus</span>
                          <ChevronRight className="h-3 w-3 ml-1" />
                        </div>
                      </CardContent>
                    </Card>
                  ))}
                  
                  {/* Loading more indicator */}
                  {displayedResults < searchResults.length && (
                    <div className="text-center py-2 text-xs text-muted-foreground">
                      Showing {displayedResults} of {searchResults.length} results
                    </div>
                  )}
                </div>
              </ScrollArea>

              {/* Results Summary */}
              <div className="text-xs text-muted-foreground text-center pt-2 border-t">
                Found {searchResults.length} result{searchResults.length !== 1 ? 's' : ''}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};