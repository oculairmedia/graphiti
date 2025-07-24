import React, { createContext, useContext, useState, ReactNode } from 'react';

interface GraphConfig {
  // Physics
  gravity: number;
  repulsion: number;
  centerForce: number;
  friction: number;
  linkSpring: number;
  linkDistance: number;
  mouseRepulsion: number;
  simulationDecay: number;
  
  // Appearance
  linkWidth: number;
  linkOpacity: number;
  linkColor: string;
  backgroundColor: string;
  
  // Curved Links
  curvedLinks: boolean;
  curvedLinkSegments: number;
  curvedLinkWeight: number;
  curvedLinkControlPointDistance: number;
  
  // Node sizing
  minNodeSize: number;
  maxNodeSize: number;
  sizeMultiplier: number;
  nodeOpacity: number;
  sizeMapping: string;
  borderWidth: number;
  
  // Node colors by type
  nodeTypeColors: {
    Entity: string;
    Episodic: string;
    Agent: string;
    Community: string;
  };
  nodeTypeVisibility: {
    Entity: boolean;
    Episodic: boolean;
    Agent: boolean;
    Community: boolean;
  };
  
  // Labels
  showLabels: boolean;
  showHoveredNodeLabel: boolean;
  labelColor: string;
  hoveredLabelColor: string;
  labelSize: number;
  labelOpacity: number;
  
  // Visual preferences
  colorScheme: string;
  
  // Query
  queryType: string;
  nodeLimit: number;
}

interface GraphConfigContextType {
  config: GraphConfig;
  updateConfig: (updates: Partial<GraphConfig>) => void;
  cosmographRef: React.MutableRefObject<any> | null;
  setCosmographRef: (ref: React.MutableRefObject<any>) => void;
  // Graph control methods
  zoomIn: () => void;
  zoomOut: () => void;
  fitView: () => void;
}

const defaultConfig: GraphConfig = {
  // Physics
  gravity: 0.05,
  repulsion: 0.1,
  centerForce: 0.1,
  friction: 0.85,
  linkSpring: 1.0,
  linkDistance: 2,
  mouseRepulsion: 2.0,
  simulationDecay: 1000,
  
  // Appearance
  linkWidth: 1,
  linkOpacity: 0.8,
  linkColor: '#666666',
  backgroundColor: '#0a0a0a',
  
  // Curved Links
  curvedLinks: false,
  curvedLinkSegments: 19,
  curvedLinkWeight: 0.8,
  curvedLinkControlPointDistance: 0.5,
  
  // Node sizing
  minNodeSize: 3,
  maxNodeSize: 12,
  sizeMultiplier: 1.0,
  nodeOpacity: 90, // Using percentage (0-100)
  sizeMapping: 'degree',
  borderWidth: 0,
  
  // Node colors by type
  nodeTypeColors: {
    Entity: '#4ECDC4',
    Episodic: '#B794F6', 
    Agent: '#F6AD55',
    Community: '#90CDF4'
  },
  nodeTypeVisibility: {
    Entity: true,
    Episodic: true,
    Agent: true,
    Community: true
  },
  
  // Labels
  showLabels: true,
  showHoveredNodeLabel: true,
  labelColor: '#ffffff',
  hoveredLabelColor: '#ffffff',
  labelSize: 12,
  labelOpacity: 80, // Using percentage (0-100)
  
  // Visual preferences
  colorScheme: 'by-type',
  
  // Query
  queryType: 'entire_graph',
  nodeLimit: 100000,
};

const GraphConfigContext = createContext<GraphConfigContextType | undefined>(undefined);

export const GraphConfigProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [config, setConfig] = useState<GraphConfig>(defaultConfig);
  const [cosmographRef, setCosmographRef] = useState<React.MutableRefObject<any> | null>(null);

  const updateConfig = (updates: Partial<GraphConfig>) => {
    setConfig(prev => {
      const newConfig = { ...prev, ...updates };
      // Note: Updates will be applied through React props in GraphCanvas
      // Cosmograph React component handles updates automatically through props
      return newConfig;
    });
  };

  const zoomIn = () => {
    if (cosmographRef?.current) {
      const currentZoom = cosmographRef.current.getZoomLevel();
      cosmographRef.current.setZoomLevel(currentZoom * 1.5, 250);
    }
  };

  const zoomOut = () => {
    if (cosmographRef?.current) {
      const currentZoom = cosmographRef.current.getZoomLevel();
      cosmographRef.current.setZoomLevel(currentZoom * 0.7, 250);
    }
  };

  const fitView = () => {
    if (cosmographRef?.current) {
      cosmographRef.current.fitView();
    }
  };

  return (
    <GraphConfigContext.Provider value={{ 
      config, 
      updateConfig, 
      cosmographRef, 
      setCosmographRef,
      zoomIn,
      zoomOut,
      fitView
    }}>
      {children}
    </GraphConfigContext.Provider>
  );
};

export const useGraphConfig = () => {
  const context = useContext(GraphConfigContext);
  if (!context) {
    throw new Error('useGraphConfig must be used within a GraphConfigProvider');
  }
  return context;
};