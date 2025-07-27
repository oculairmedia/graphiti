import React, { useCallback, useState } from 'react';
import { X, Pin, Eye, EyeOff, Copy, Download, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { GraphNode } from '../api/types';
import { useGraphConfig } from '../contexts/GraphConfigContext';
import { CollapsibleSection, type SectionConfig } from '@/components/ui/CollapsibleSection';
import { DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors } from '@dnd-kit/core';
import { arrayMove, SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import { usePersistedSections } from '@/hooks/usePersistedConfig';
import { useNodeCentralityWithFallback } from '@/hooks/useCentrality';

interface NodeDetailsPanelProps {
  node: GraphNode;
  onClose: () => void;
  onShowNeighbors?: (nodeId: string) => void;
}

export const NodeDetailsPanel: React.FC<NodeDetailsPanelProps> = ({ 
  node, 
  onClose,
  onShowNeighbors
}) => {
  const { config } = useGraphConfig();

  // Default section configuration
  const defaultSections: SectionConfig[] = [
    { id: 'summary', title: 'Summary', isCollapsed: false, order: 0, isVisible: true },
    { id: 'properties', title: 'Properties', isCollapsed: true, order: 1, isVisible: true },
    { id: 'centrality', title: 'Centrality Metrics', isCollapsed: false, order: 2, isVisible: true },
    { id: 'connections', title: 'Connections', isCollapsed: false, order: 3, isVisible: true },
    { id: 'timestamps', title: 'Timeline', isCollapsed: false, order: 4, isVisible: true },
    { id: 'actions', title: 'Actions', isCollapsed: false, order: 5, isVisible: true },
  ];

  // Section state management with persistence
  const [sections, setPersistedSections, isSectionsLoaded] = usePersistedSections(defaultSections);
  
  // State for summary expansion
  const [isSummaryExpanded, setIsSummaryExpanded] = useState(false);

  // Drag and drop sensors
  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor)
  );

  // Handle section reordering
  const handleDragEnd = (event: any) => {
    const { active, over } = event;

    if (active.id !== over.id) {
      setPersistedSections((sections) => {
        const oldIndex = sections.findIndex((section) => section.id === active.id);
        const newIndex = sections.findIndex((section) => section.id === over.id);

        const newSections = arrayMove(sections, oldIndex, newIndex);
        // Update order values
        return newSections.map((section, index) => ({
          ...section,
          order: index
        }));
      });
    }
  };

  // Handle section collapse toggle
  const handleToggleCollapse = (sectionId: string) => {
    setPersistedSections((sections) =>
      sections.map((section) =>
        section.id === sectionId
          ? { ...section, isCollapsed: !section.isCollapsed }
          : section
      )
    );
  };

  // Get section by id
  const getSection = (id: string) => sections.find(s => s.id === id) || defaultSections.find(s => s.id === id)!;
  
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

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Use centrality hook with fallback
  const { centrality, isLoading: centralityLoading, source } = useNodeCentralityWithFallback(node.id, node.properties);

  // Use real node data
  const data = {
    id: node.id,
    name: node.label || node.id,
    type: node.node_type || 'Unknown',
    summary: node.summary || node.description || node.properties?.summary || node.properties?.content || node.properties?.source_description || '',
    properties: node.properties || {},
    centrality: centrality || {
      degree: 0,
      betweenness: 0,
      pagerank: 0,
      eigenvector: 0
    },
    timestamps: {
      created: node.created_at || node.properties?.created || new Date().toISOString(),
      updated: node.updated_at || node.properties?.updated || new Date().toISOString()
    },
    connections: node.properties?.degree || node.properties?.connections || 0
  };

  return (
    <Card className="glass-panel w-96 max-h-[80vh] overflow-hidden animate-fade-in flex flex-col min-w-0">
      <CardHeader className="pb-3 flex-shrink-0">
        <div className="flex items-start justify-between">
          <div className="flex-1 pr-2 min-w-0">
            <CardTitle className="text-lg leading-tight mb-2 break-words overflow-wrap-anywhere">
              {data.name}
            </CardTitle>
            <div className="flex items-center space-x-2 mb-2">
              <Badge 
                className={`text-xs border-0 ${
                  getBadgeHslColor(data.type) ? 'details-badge' : 'details-badge-default'
                }`}
                style={getBadgeHslColor(data.type) ? {
                  '--badge-color': getBadgeHslColor(data.type)
                } as React.CSSProperties : undefined}
              >
                {data.type}
              </Badge>
              <Badge variant="outline" className="text-xs">
                ID: {data.id.slice(-6)}
              </Badge>
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            className="hover:bg-destructive/10"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>

      <CardContent className="flex-1 overflow-y-auto custom-scrollbar space-y-3 min-h-0 min-w-0">
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
          modifiers={[restrictToVerticalAxis]}
        >
          <SortableContext items={sections.map(s => s.id)} strategy={verticalListSortingStrategy}>
            {sections
              .sort((a, b) => a.order - b.order)
              .map((section) => {
                const sectionProps = { section, onToggleCollapse: handleToggleCollapse };
                
                switch (section.id) {
                  case 'summary':
                    if (!data.summary) return null;
                    
                    const TRUNCATE_LENGTH = 200;
                    const needsTruncation = data.summary.length > TRUNCATE_LENGTH;
                    const displaySummary = needsTruncation && !isSummaryExpanded 
                      ? data.summary.substring(0, TRUNCATE_LENGTH) + '...'
                      : data.summary;
                    
                    return (
                      <CollapsibleSection key={section.id} {...sectionProps}>
                        <div 
                          className={`text-sm leading-relaxed break-words overflow-wrap-anywhere ${
                            needsTruncation && !isSummaryExpanded ? 'cursor-pointer' : ''
                          }`}
                          onClick={() => needsTruncation && setIsSummaryExpanded(!isSummaryExpanded)}
                        >
                          <p>{displaySummary}</p>
                          {needsTruncation && (
                            <button
                              className="text-xs text-primary hover:text-primary/80 mt-1 focus:outline-none"
                              onClick={(e) => {
                                e.stopPropagation();
                                setIsSummaryExpanded(!isSummaryExpanded);
                              }}
                            >
                              {isSummaryExpanded ? 'Show less' : 'Show more'}
                            </button>
                          )}
                        </div>
                      </CollapsibleSection>
                    );

                  case 'properties':
                    return (
                      <CollapsibleSection key={section.id} {...sectionProps}>
                        <div className="space-y-2 min-w-0">
                          {Object.entries(data.properties).map(([key, value]) => (
                            <div key={key} className="flex justify-between items-start gap-2 min-w-0">
                              <span className="text-xs text-muted-foreground capitalize flex-shrink-0">
                                {key.replace(/([A-Z])/g, ' $1')}:
                              </span>
                              <span className="text-xs text-right flex-1 min-w-0 break-words overflow-wrap-anywhere">
                                {Array.isArray(value) ? value.join(', ') : String(value)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </CollapsibleSection>
                    );

                  case 'centrality':
                    return (
                      <CollapsibleSection key={section.id} {...sectionProps}>
                        <div className="space-y-3">
                          {centralityLoading && source === 'none' ? (
                            <div className="text-xs text-muted-foreground text-center py-2">
                              Loading centrality metrics...
                            </div>
                          ) : (
                            <>
                              {source === 'api' && (
                                <Badge variant="outline" className="text-xs mb-2">
                                  Live Data
                                </Badge>
                              )}
                              {Object.entries(data.centrality).map(([metric, value]) => (
                                <div key={metric}>
                                  <div className="flex justify-between items-center mb-1">
                                    <span className="text-xs capitalize">
                                      {metric.replace(/([A-Z])/g, ' $1')}
                                    </span>
                                    <span className="text-xs text-primary font-medium">
                                      {(Number(value) * 100).toFixed(1)}%
                                    </span>
                                  </div>
                                  <Progress 
                                    value={Number(value) * 100} 
                                    className="h-1.5"
                                  />
                                </div>
                              ))}
                            </>
                          )}
                        </div>
                      </CollapsibleSection>
                    );

                  case 'connections':
                    return (
                      <CollapsibleSection key={section.id} {...sectionProps}>
                        <div className="flex items-center justify-between">
                          <span className="text-xs">Related Nodes:</span>
                          <Badge variant="secondary" className="text-xs">
                            {data.connections}
                          </Badge>
                        </div>
                      </CollapsibleSection>
                    );

                  case 'timestamps':
                    return (
                      <CollapsibleSection key={section.id} {...sectionProps}>
                        <div className="space-y-1">
                          <div className="flex justify-between items-center">
                            <span className="text-xs text-muted-foreground">Created:</span>
                            <span className="text-xs">{formatDate(data.timestamps.created)}</span>
                          </div>
                          <div className="flex justify-between items-center">
                            <span className="text-xs text-muted-foreground">Updated:</span>
                            <span className="text-xs">{formatDate(data.timestamps.updated)}</span>
                          </div>
                        </div>
                      </CollapsibleSection>
                    );

                  case 'actions':
                    return (
                      <CollapsibleSection key={section.id} {...sectionProps}>
                        <div className="space-y-2">
                          <div className="grid grid-cols-2 gap-2">
                            <Button variant="outline" size="sm" className="h-8">
                              <Pin className="h-3 w-3 mr-1" />
                              Pin
                            </Button>
                            <Button variant="outline" size="sm" className="h-8">
                              <Eye className="h-3 w-3 mr-1" />
                              Focus
                            </Button>
                            <Button variant="outline" size="sm" className="h-8">
                              <Copy className="h-3 w-3 mr-1" />
                              Copy ID
                            </Button>
                            <Button variant="outline" size="sm" className="h-8">
                              <Download className="h-3 w-3 mr-1" />
                              Export
                            </Button>
                          </div>

                          <Button 
                            variant="secondary" 
                            className="w-full h-8" 
                            size="sm"
                            onClick={() => onShowNeighbors?.(data.id)}
                            disabled={!onShowNeighbors}
                          >
                            <ExternalLink className="h-3 w-3 mr-2" />
                            Show Neighbors
                          </Button>
                        </div>
                      </CollapsibleSection>
                    );

                  default:
                    return null;
                }
              })}
          </SortableContext>
        </DndContext>
      </CardContent>
    </Card>
  );
};