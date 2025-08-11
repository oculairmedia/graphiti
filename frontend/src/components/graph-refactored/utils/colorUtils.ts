/**
 * Color utilities for node and edge styling
 */

// Default color palette
export const defaultColors = {
  node: {
    default: '#6366f1',
    selected: '#fbbf24',
    hover: '#60a5fa',
    highlighted: '#f59e0b',
    muted: '#94a3b8'
  },
  edge: {
    default: '#94a3b8',
    selected: '#fbbf24',
    hover: '#60a5fa',
    highlighted: '#f59e0b',
    muted: '#cbd5e1'
  },
  nodeTypes: {
    Entity: '#6366f1',
    Episodic: '#10b981',
    Relation: '#f59e0b',
    Unknown: '#94a3b8'
  }
} as const;

// Convert hex to RGB
export function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16)
  } : null;
}

// Convert RGB to hex
export function rgbToHex(r: number, g: number, b: number): string {
  return '#' + [r, g, b].map(x => {
    const hex = x.toString(16);
    return hex.length === 1 ? '0' + hex : hex;
  }).join('');
}

// Lighten a color
export function lightenColor(color: string, amount: number): string {
  const rgb = hexToRgb(color);
  if (!rgb) return color;
  
  const r = Math.min(255, Math.round(rgb.r + (255 - rgb.r) * amount));
  const g = Math.min(255, Math.round(rgb.g + (255 - rgb.g) * amount));
  const b = Math.min(255, Math.round(rgb.b + (255 - rgb.b) * amount));
  
  return rgbToHex(r, g, b);
}

// Darken a color
export function darkenColor(color: string, amount: number): string {
  const rgb = hexToRgb(color);
  if (!rgb) return color;
  
  const r = Math.max(0, Math.round(rgb.r * (1 - amount)));
  const g = Math.max(0, Math.round(rgb.g * (1 - amount)));
  const b = Math.max(0, Math.round(rgb.b * (1 - amount)));
  
  return rgbToHex(r, g, b);
}

// Get color with opacity
export function colorWithOpacity(color: string, opacity: number): string {
  const rgb = hexToRgb(color);
  if (!rgb) return color;
  
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${opacity})`;
}

// Interpolate between two colors
export function interpolateColor(color1: string, color2: string, ratio: number): string {
  const rgb1 = hexToRgb(color1);
  const rgb2 = hexToRgb(color2);
  
  if (!rgb1 || !rgb2) return color1;
  
  const r = Math.round(rgb1.r + (rgb2.r - rgb1.r) * ratio);
  const g = Math.round(rgb1.g + (rgb2.g - rgb1.g) * ratio);
  const b = Math.round(rgb1.b + (rgb2.b - rgb1.b) * ratio);
  
  return rgbToHex(r, g, b);
}

// Generate color scale
export function generateColorScale(baseColor: string, steps: number): string[] {
  const colors: string[] = [];
  
  for (let i = 0; i < steps; i++) {
    const ratio = i / (steps - 1);
    if (ratio < 0.5) {
      // Darken for first half
      colors.push(darkenColor(baseColor, (0.5 - ratio) * 0.6));
    } else {
      // Lighten for second half
      colors.push(lightenColor(baseColor, (ratio - 0.5) * 0.6));
    }
  }
  
  return colors;
}

// Get color by centrality value (0-1)
export function getColorByCentrality(centrality: number, colorScale?: string[]): string {
  const scale = colorScale || generateColorScale('#6366f1', 10);
  const index = Math.floor(centrality * (scale.length - 1));
  return scale[Math.min(index, scale.length - 1)];
}

// Get node color by type
export function getNodeColorByType(nodeType: string): string {
  return defaultColors.nodeTypes[nodeType as keyof typeof defaultColors.nodeTypes] || 
         defaultColors.nodeTypes.Unknown;
}

// Color generator for unique colors
export class ColorGenerator {
  private hue = 0;
  private readonly step = 137.5; // Golden angle
  
  next(): string {
    const color = `hsl(${this.hue}, 70%, 60%)`;
    this.hue = (this.hue + this.step) % 360;
    return color;
  }
  
  reset(): void {
    this.hue = 0;
  }
}