/**
 * Color Utilities Hook
 * 
 * GRAPH-84: Thin wrapper around centralized NodeColorManager utilities
 * Provides React hook interface for color operations
 */

import { useCallback, useMemo } from 'react';
import { hexToRgba, generateHSLColor } from '@/utils/NodeColorManager';

/**
 * Custom hook for color utility functions
 */
export function useColorUtils() {
  /**
   * Convert hex color to HSL for CSS custom properties
   */
  const hexToHsl = useCallback((hex: string): string => {
    const cleanHex = hex.replace('#', '');
    
    const r = parseInt(cleanHex.substr(0, 2), 16) / 255;
    const g = parseInt(cleanHex.substr(2, 2), 16) / 255;
    const b = parseInt(cleanHex.substr(4, 2), 16) / 255;
    
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const delta = max - min;
    
    const l = (max + min) / 2;
    
    let s = 0;
    if (delta !== 0) {
      s = delta / (1 - Math.abs(2 * l - 1));
    }
    
    let h = 0;
    if (delta !== 0) {
      if (max === r) {
        h = ((g - b) / delta) % 6;
      } else if (max === g) {
        h = (b - r) / delta + 2;
      } else {
        h = (r - g) / delta + 4;
      }
      h = Math.round(h * 60);
      if (h < 0) h += 360;
    }
    
    const sPercent = Math.round(s * 100);
    const lPercent = Math.round(l * 100);
    
    return `${h} ${sPercent}% ${lPercent}%`;
  }, []);

  /**
   * Convert hex color to RGBA - delegates to centralized utility
   */
  const hexToRgbaCallback = useCallback((hex: string, opacity: number = 1): string => {
    return hexToRgba(hex, opacity);
  }, []);

  /**
   * Generate HSL color - delegates to centralized utility
   */
  const generateHSLColorCallback = useCallback((scheme: string, factor: number, opacity: number = 1): string => {
    return generateHSLColor(scheme, factor, opacity);
  }, []);

  /**
   * Get contrasting text color (black or white) based on background color
   */
  const getContrastingTextColor = useCallback((backgroundColor: string): string => {
    const cleanHex = backgroundColor.replace('#', '');
    
    const r = parseInt(cleanHex.substr(0, 2), 16);
    const g = parseInt(cleanHex.substr(2, 2), 16);
    const b = parseInt(cleanHex.substr(4, 2), 16);
    
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    
    return luminance > 0.5 ? '#000000' : '#FFFFFF';
  }, []);

  /**
   * Generate a color palette
   */
  const generateColorPalette = useCallback((baseColor: string, count: number = 5): string[] => {
    const hsl = hexToHsl(baseColor);
    const [h, s, l] = hsl.split(' ').map(v => parseInt(v));
    
    const palette: string[] = [];
    const step = 20;
    
    for (let i = 0; i < count; i++) {
      const lightness = Math.max(10, Math.min(90, l + (i - Math.floor(count / 2)) * step));
      palette.push(`hsl(${h}, ${s}%, ${lightness}%)`);
    }
    
    return palette;
  }, [hexToHsl]);

  return useMemo(() => ({
    hexToHsl,
    hexToRgba: hexToRgbaCallback,
    generateHSLColor: generateHSLColorCallback,
    getContrastingTextColor,
    generateColorPalette,
  }), [hexToHsl, hexToRgbaCallback, generateHSLColorCallback, getContrastingTextColor, generateColorPalette]);
}
