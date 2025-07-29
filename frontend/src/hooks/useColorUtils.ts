import { useCallback } from 'react';
import { hexToRgba as hexToRgbaUtil, generateHSLColor as generateHSLColorUtil } from '../utils/colorCache';

/**
 * Custom hook for color utility functions
 */
export function useColorUtils() {
  /**
   * Convert hex color to HSL for CSS custom properties
   */
  const hexToHsl = useCallback((hex: string): string => {
    // Remove # if present
    const cleanHex = hex.replace('#', '');
    
    // Convert hex to RGB
    const r = parseInt(cleanHex.substr(0, 2), 16) / 255;
    const g = parseInt(cleanHex.substr(2, 2), 16) / 255;
    const b = parseInt(cleanHex.substr(4, 2), 16) / 255;
    
    // Find greatest and smallest channel values
    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    const delta = max - min;
    
    // Calculate lightness
    const l = (max + min) / 2;
    
    // Calculate saturation
    let s = 0;
    if (delta !== 0) {
      s = delta / (1 - Math.abs(2 * l - 1));
    }
    
    // Calculate hue
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
    
    // Convert to percentages
    const sPercent = Math.round(s * 100);
    const lPercent = Math.round(l * 100);
    
    return `${h} ${sPercent}% ${lPercent}%`;
  }, []);

  /**
   * Convert hex color to RGBA
   */
  const hexToRgba = useCallback((hex: string, opacity: number = 1): string => {
    return hexToRgbaUtil(hex, opacity);
  }, []);

  /**
   * Generate HSL color based on scheme and factor
   */
  const generateHSLColor = useCallback((scheme: string, factor: number, opacity: number = 1): string => {
    return generateHSLColorUtil(scheme, factor, opacity);
  }, []);

  /**
   * Get contrasting text color (black or white) based on background color
   */
  const getContrastingTextColor = useCallback((backgroundColor: string): string => {
    // Remove # if present
    const cleanHex = backgroundColor.replace('#', '');
    
    // Convert to RGB
    const r = parseInt(cleanHex.substr(0, 2), 16);
    const g = parseInt(cleanHex.substr(2, 2), 16);
    const b = parseInt(cleanHex.substr(4, 2), 16);
    
    // Calculate relative luminance
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    
    // Return black for light backgrounds, white for dark
    return luminance > 0.5 ? '#000000' : '#FFFFFF';
  }, []);

  /**
   * Generate a color palette
   */
  const generateColorPalette = useCallback((baseColor: string, count: number = 5): string[] => {
    const hsl = hexToHsl(baseColor);
    const [h, s, l] = hsl.split(' ').map(v => parseInt(v));
    
    const palette: string[] = [];
    const step = 20; // Lightness step
    
    for (let i = 0; i < count; i++) {
      const lightness = Math.max(10, Math.min(90, l + (i - Math.floor(count / 2)) * step));
      palette.push(`hsl(${h}, ${s}%, ${lightness}%)`);
    }
    
    return palette;
  }, [hexToHsl]);

  return {
    hexToHsl,
    hexToRgba,
    generateHSLColor,
    getContrastingTextColor,
    generateColorPalette,
  };
}