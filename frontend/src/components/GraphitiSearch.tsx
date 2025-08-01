import React, { useRef, useState, useCallback, useEffect } from 'react';
import { Search, X, AlertCircle, Loader2, ChevronRight, Calendar, Tag } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
    <Card className={cn("glass border-border/30 flex flex-col h-full", className)}>
      <CardHeader className="pb-3 flex-shrink-0">
        <CardTitle className="text-sm flex items-center space-x-2">
          <Search className="h-4 w-4 text-primary" />
          <span>Knowledge Search</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 flex flex-col p-0 px-3 pb-3 min-h-0">
          {/* Search Input */}
          <div className="relative flex-shrink-0 mb-2">
            <Input
              ref={inputRef}
              type="text"
              placeholder="Search entities, concepts..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => setIsExpanded(true)}
              className="pr-10 h-8 text-sm"
            />
            {searchQuery && (
              <Button
                variant="ghost"
                size="sm"
                className="absolute right-1 top-0.5 h-7 w-7 p-0"
                onClick={handleClear}
              >
                <X className="h-3 w-3" />
              </Button>
            )}
          </div>

          {/* Search Results */}
          {isExpanded && searchQuery && (
            <div className="flex-1 flex flex-col min-h-0">
              {isSearching && (
                <div className="flex items-center justify-center py-3">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              )}

              {searchError && (
                <Alert variant="destructive" className="py-2">
                  <AlertCircle className="h-3 w-3" />
                  <AlertDescription className="text-xs">
                    {searchError instanceof Error ? searchError.message : 'Search failed'}
                  </AlertDescription>
                </Alert>
              )}

              {!isSearching && !searchError && searchResults.length === 0 && (
                <div className="text-center py-3 text-xs text-muted-foreground">
                  No results found for "{searchQuery}"
                </div>
              )}

              {searchResults.length > 0 && (
                <div className="flex-1 flex flex-col overflow-hidden">
                  <ScrollArea className="flex-1" ref={scrollRef} onScrollCapture={handleScroll}>
                    <div className="space-y-1.5 pr-2">
                      {searchResults.slice(0, displayedResults).map((node) => (
                        <div
                          key={node.uuid}
                          className={cn(
                            'cursor-pointer transition-all p-2 rounded-md border bg-secondary/30 hover:bg-secondary/50',
                            selectedNodeId === node.uuid && 'ring-1 ring-primary'
                          )}
                          onClick={() => selectNode(node)}
                        >
                          {/* Node Name and Type */}
                          <div className="flex items-start justify-between gap-1 mb-1">
                            <h4 className="font-medium text-xs line-clamp-1 flex-1">
                              {node.name}
                            </h4>
                            <Badge variant="secondary" className="text-[10px] px-1 py-0 shrink-0">
                              {node.labels[0] || 'Entity'}
                            </Badge>
                          </div>

                          {/* Summary */}
                          {node.summary && (
                            <p className="text-[11px] text-muted-foreground line-clamp-2 mb-1">
                              {node.summary}
                            </p>
                          )}

                          {/* Metadata */}
                          <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                            <div className="flex items-center gap-0.5">
                              <Calendar className="h-2.5 w-2.5" />
                              <span>{formatDate(node.created_at)}</span>
                            </div>
                            {getCentralityScore(node) > 1 && (
                              <Badge variant="outline" className="text-[10px] px-1 py-0 h-4">
                                {getCentralityScore(node).toFixed(0)}%
                              </Badge>
                            )}
                          </div>
                        </div>
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
                  <div className="text-[10px] text-muted-foreground text-center pt-1 border-t flex-shrink-0">
                    Found {searchResults.length} result{searchResults.length !== 1 ? 's' : ''}
                  </div>
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
  );
};