import { createContext, useContext } from 'react';
import type { GraphConfigContextType } from './GraphConfigContextTypes';

export const GraphConfigContext = createContext<GraphConfigContextType | undefined>(undefined);

export const useGraphConfig = () => {
  const context = useContext(GraphConfigContext);
  if (!context) {
    throw new Error('useGraphConfig must be used within a GraphConfigProvider');
  }
  return context;
};