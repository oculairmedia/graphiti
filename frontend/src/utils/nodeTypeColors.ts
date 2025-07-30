// Generate default colors for dynamic node types
export const generateNodeTypeColor = (nodeType: string, index: number): string => {
  // Predefined color palette for common node types
  const colorPalette = [
    '#4ECDC4', // Teal
    '#B794F6', // Purple  
    '#F6AD55', // Orange
    '#90CDF4', // Blue
    '#FF6B6B', // Red
    '#4ADE80', // Green
    '#FBBF24', // Yellow
    '#EC4899', // Pink
    '#8B5CF6', // Violet
    '#06B6D4', // Cyan
    '#F59E0B', // Amber
    '#EF4444'  // Red variant
  ];
  
  // Use specific colors for known node types
  const knownTypeColors: Record<string, string> = {
    'Entity': '#B794F6',    // Purple
    'Episodic': '#4ECDC4',  // Teal
    'Agent': '#F6AD55',     // Orange
    'Community': '#90CDF4', // Blue
    'Unknown': '#9CA3AF'    // Gray
  };
  
  if (knownTypeColors[nodeType]) {
    return knownTypeColors[nodeType];
  }
  
  // For unknown types, use the color palette cyclically
  return colorPalette[index % colorPalette.length];
};