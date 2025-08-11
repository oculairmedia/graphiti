import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { GraphNode } from '../../../api/types';

interface SearchResult {
  node: GraphNode;
  score: number;
  matches: {
    field: string;
    value: string;
    indices: [number, number][];
  }[];
}

interface SearchConfig {
  fields?: string[];
  fuzzy?: boolean;
  threshold?: number;
  limit?: number;
  caseSensitive?: boolean;
  includeScore?: boolean;
  sortBy?: 'score' | 'alphabetical' | 'centrality';
  debounceMs?: number;
}

interface SearchManagerProps {
  nodes: GraphNode[];
  config?: SearchConfig;
  onSearchResults?: (results: SearchResult[]) => void;
  onSearchStateChange?: (isSearching: boolean) => void;
  children?: React.ReactNode;
}

interface SearchState {
  query: string;
  results: SearchResult[];
  isSearching: boolean;
  selectedIndex: number;
  history: string[];
  suggestions: string[];
}

/**
 * SearchManager - Advanced search functionality for graph nodes
 * Supports fuzzy search, field-specific search, and search history
 */
export const SearchManager: React.FC<SearchManagerProps> = React.memo(({
  nodes,
  config = {},
  onSearchResults,
  onSearchStateChange,
  children
}) => {
  const [state, setState] = useState<SearchState>({
    query: '',
    results: [],
    isSearching: false,
    selectedIndex: -1,
    history: [],
    suggestions: []
  });

  const searchIndexRef = useRef<Map<string, Set<GraphNode>>>(new Map());
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Default configuration
  const fullConfig: Required<SearchConfig> = {
    fields: config.fields || ['id', 'label', 'node_type'],
    fuzzy: config.fuzzy ?? true,
    threshold: config.threshold ?? 0.3,
    limit: config.limit ?? 100,
    caseSensitive: config.caseSensitive ?? false,
    includeScore: config.includeScore ?? true,
    sortBy: config.sortBy ?? 'score',
    debounceMs: config.debounceMs ?? 300
  };

  // Build search index
  useEffect(() => {
    const index = new Map<string, Set<GraphNode>>();
    
    nodes.forEach(node => {
      // Index each field
      fullConfig.fields.forEach(field => {
        const value = getFieldValue(node, field);
        if (value) {
          const normalizedValue = fullConfig.caseSensitive 
            ? value.toString() 
            : value.toString().toLowerCase();
          
          // Index all substrings for faster search
          for (let i = 0; i < normalizedValue.length; i++) {
            for (let j = i + 1; j <= normalizedValue.length; j++) {
              const substring = normalizedValue.substring(i, j);
              if (!index.has(substring)) {
                index.set(substring, new Set());
              }
              index.get(substring)!.add(node);
            }
          }
        }
      });
    });
    
    searchIndexRef.current = index;
  }, [nodes, fullConfig.fields, fullConfig.caseSensitive]);

  // Get field value from node
  const getFieldValue = (node: GraphNode, field: string): any => {
    const parts = field.split('.');
    let value: any = node;
    
    for (const part of parts) {
      value = value?.[part];
      if (value === undefined) break;
    }
    
    return value;
  };

  // Fuzzy string matching
  const fuzzyMatch = (query: string, text: string): { match: boolean; score: number; indices: [number, number][] } => {
    if (!fullConfig.fuzzy) {
      const index = text.indexOf(query);
      return {
        match: index !== -1,
        score: index !== -1 ? 1 : 0,
        indices: index !== -1 ? [[index, index + query.length - 1]] : []
      };
    }

    const pattern = query.toLowerCase();
    const str = text.toLowerCase();
    let patternIdx = 0;
    let strIdx = 0;
    let score = 0;
    const indices: [number, number][] = [];
    let inMatch = false;
    let matchStart = -1;

    while (strIdx < str.length && patternIdx < pattern.length) {
      if (str[strIdx] === pattern[patternIdx]) {
        if (!inMatch) {
          matchStart = strIdx;
          inMatch = true;
        }
        score += 1 / (strIdx + 1); // Higher score for earlier matches
        patternIdx++;
      } else if (inMatch) {
        indices.push([matchStart, strIdx - 1]);
        inMatch = false;
      }
      strIdx++;
    }

    if (inMatch) {
      indices.push([matchStart, strIdx - 1]);
    }

    return {
      match: patternIdx === pattern.length,
      score: patternIdx === pattern.length ? score / pattern.length : 0,
      indices
    };
  };

  // Perform search
  const performSearch = useCallback((query: string) => {
    if (!query.trim()) {
      setState(prev => ({ ...prev, results: [], isSearching: false }));
      onSearchResults?.([]);
      return;
    }

    setState(prev => ({ ...prev, isSearching: true }));
    onSearchStateChange?.(true);

    const normalizedQuery = fullConfig.caseSensitive ? query : query.toLowerCase();
    const results: SearchResult[] = [];
    const scoreMap = new Map<GraphNode, SearchResult>();

    // Search through nodes
    nodes.forEach(node => {
      let bestScore = 0;
      const matches: SearchResult['matches'] = [];

      fullConfig.fields.forEach(field => {
        const value = getFieldValue(node, field);
        if (value) {
          const text = value.toString();
          const matchResult = fuzzyMatch(normalizedQuery, text);
          
          if (matchResult.match && matchResult.score > fullConfig.threshold) {
            bestScore = Math.max(bestScore, matchResult.score);
            matches.push({
              field,
              value: text,
              indices: matchResult.indices
            });
          }
        }
      });

      if (matches.length > 0) {
        scoreMap.set(node, {
          node,
          score: bestScore,
          matches
        });
      }
    });

    // Convert to array and sort
    results.push(...Array.from(scoreMap.values()));
    
    // Sort results
    switch (fullConfig.sortBy) {
      case 'score':
        results.sort((a, b) => b.score - a.score);
        break;
      case 'alphabetical':
        results.sort((a, b) => (a.node.label || a.node.id).localeCompare(b.node.label || b.node.id));
        break;
      case 'centrality':
        results.sort((a, b) => {
          const aCentrality = a.node.properties?.degree_centrality || 0;
          const bCentrality = b.node.properties?.degree_centrality || 0;
          return bCentrality - aCentrality;
        });
        break;
    }

    // Apply limit
    const limitedResults = results.slice(0, fullConfig.limit);

    setState(prev => ({
      ...prev,
      results: limitedResults,
      isSearching: false,
      selectedIndex: limitedResults.length > 0 ? 0 : -1
    }));

    onSearchResults?.(limitedResults);
    onSearchStateChange?.(false);
  }, [nodes, fullConfig, onSearchResults, onSearchStateChange]);

  // Debounced search
  const search = useCallback((query: string) => {
    setState(prev => ({ ...prev, query }));

    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }

    debounceTimerRef.current = setTimeout(() => {
      performSearch(query);
      
      // Update history
      if (query.trim() && !state.history.includes(query)) {
        setState(prev => ({
          ...prev,
          history: [query, ...prev.history.slice(0, 9)] // Keep last 10
        }));
      }
    }, fullConfig.debounceMs);
  }, [performSearch, fullConfig.debounceMs, state.history]);

  // Generate suggestions based on current input
  const generateSuggestions = useCallback((query: string) => {
    if (!query.trim()) {
      setState(prev => ({ ...prev, suggestions: [] }));
      return;
    }

    const normalizedQuery = fullConfig.caseSensitive ? query : query.toLowerCase();
    const suggestions = new Set<string>();

    // Get potential completions from index
    searchIndexRef.current.forEach((nodes, substring) => {
      if (substring.startsWith(normalizedQuery)) {
        nodes.forEach(node => {
          fullConfig.fields.forEach(field => {
            const value = getFieldValue(node, field);
            if (value) {
              const text = value.toString();
              if (text.toLowerCase().includes(normalizedQuery)) {
                suggestions.add(text);
              }
            }
          });
        });
      }
    });

    setState(prev => ({
      ...prev,
      suggestions: Array.from(suggestions).slice(0, 10)
    }));
  }, [fullConfig.caseSensitive, fullConfig.fields]);

  // Navigation methods
  const selectNext = useCallback(() => {
    setState(prev => ({
      ...prev,
      selectedIndex: Math.min(prev.selectedIndex + 1, prev.results.length - 1)
    }));
  }, []);

  const selectPrevious = useCallback(() => {
    setState(prev => ({
      ...prev,
      selectedIndex: Math.max(prev.selectedIndex - 1, 0)
    }));
  }, []);

  const clearSearch = useCallback(() => {
    setState(prev => ({
      ...prev,
      query: '',
      results: [],
      selectedIndex: -1,
      suggestions: []
    }));
    onSearchResults?.([]);
  }, [onSearchResults]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  // Context value
  const contextValue = useMemo(() => ({
    ...state,
    search,
    clearSearch,
    selectNext,
    selectPrevious,
    generateSuggestions,
    getSelectedResult: () => state.results[state.selectedIndex] || null
  }), [state, search, clearSearch, selectNext, selectPrevious, generateSuggestions]);

  return (
    <SearchContext.Provider value={contextValue}>
      {children}
    </SearchContext.Provider>
  );
}, (prevProps, nextProps) => {
  // Custom comparison to prevent unnecessary re-renders
  return (
    prevProps.nodes === nextProps.nodes &&
    prevProps.config === nextProps.config &&
    prevProps.children === nextProps.children &&
    prevProps.onSearchResults === nextProps.onSearchResults &&
    prevProps.onSearchStateChange === nextProps.onSearchStateChange
  );
});

// Search context
const SearchContext = React.createContext<{
  query: string;
  results: SearchResult[];
  isSearching: boolean;
  selectedIndex: number;
  history: string[];
  suggestions: string[];
  search: (query: string) => void;
  clearSearch: () => void;
  selectNext: () => void;
  selectPrevious: () => void;
  generateSuggestions: (query: string) => void;
  getSelectedResult: () => SearchResult | null;
}>({
  query: '',
  results: [],
  isSearching: false,
  selectedIndex: -1,
  history: [],
  suggestions: [],
  search: () => {},
  clearSearch: () => {},
  selectNext: () => {},
  selectPrevious: () => {},
  generateSuggestions: () => {},
  getSelectedResult: () => null
});

export const useSearch = () => React.useContext(SearchContext);