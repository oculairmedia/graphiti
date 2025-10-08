// High-performance color calculation cache for GraphCanvas
// Eliminates expensive HSL/hex conversions in render loop

interface ColorCacheEntry {
  color: string;
  timestamp: number;
  lastAccessed: number;
}

class ColorCalculationCache {
  private cache = new Map<string, ColorCacheEntry>();
  private maxSize = 10000; // Maximum cache entries
  private maxAge = 300000; // 5 minutes cache TTL

  private generateCacheKey(scheme: string, value: number, opacity: number): string {
    return `${scheme}:${Math.round(value * 1000)}:${Math.round(opacity * 100)}`;
  }

  get(scheme: string, value: number, opacity: number): string | null {
    const key = this.generateCacheKey(scheme, value, opacity);
    const entry = this.cache.get(key);
    
    if (!entry) return null;
    
    // Check if entry is stale
    if (Date.now() - entry.timestamp > this.maxAge) {
      this.cache.delete(key);
      return null;
    }
    
    // Update last accessed time for LRU tracking
    entry.lastAccessed = Date.now();
    
    return entry.color;
  }

  set(scheme: string, value: number, opacity: number, color: string): void {
    // Clear old entries if cache is full
    if (this.cache.size >= this.maxSize) {
      this.clearStaleEntries();
    }

    const key = this.generateCacheKey(scheme, value, opacity);
    const now = Date.now();
    this.cache.set(key, {
      color,
      timestamp: now,
      lastAccessed: now
    });
  }

  private clearStaleEntries(): void {
    const now = Date.now();
    const toDelete: string[] = [];

    for (const [key, entry] of this.cache) {
      if (now - entry.timestamp > this.maxAge) {
        toDelete.push(key);
      }
    }

    toDelete.forEach(key => this.cache.delete(key));

    // If still too large, remove least recently used entries (proper LRU)
    if (this.cache.size >= this.maxSize) {
      const entries = Array.from(this.cache.entries());
      entries.sort((a, b) => a[1].lastAccessed - b[1].lastAccessed);
      
      const toRemove = entries.slice(0, Math.floor(this.maxSize * 0.2));
      toRemove.forEach(([key]) => this.cache.delete(key));
    }
  }

  clear(): void {
    this.cache.clear();
  }

  getStats(): { size: number; maxSize: number; hitRatio?: number } {
    return {
      size: this.cache.size,
      maxSize: this.maxSize
    };
  }
}

// Pre-computed color utilities
export const colorCache = new ColorCalculationCache();

// Fast hex to rgba conversion with caching
export const hexToRgba = (hex: string, opacity: number): string => {
  const cached = colorCache.get('hex', hash(hex), opacity);
  if (cached) return cached;

  if (!hex.startsWith('#')) return hex;
  
  const hexClean = hex.substring(1);
  let r, g, b;
  
  if (hexClean.length === 3) {
    r = parseInt(hexClean.substring(0, 1).repeat(2), 16);
    g = parseInt(hexClean.substring(1, 2).repeat(2), 16);
    b = parseInt(hexClean.substring(2, 3).repeat(2), 16);
  } else if (hexClean.length === 6) {
    r = parseInt(hexClean.substring(0, 2), 16);
    g = parseInt(hexClean.substring(2, 4), 16);
    b = parseInt(hexClean.substring(4, 6), 16);
  } else {
    return hex;
  }
  
  const result = `rgba(${r}, ${g}, ${b}, ${opacity})`;
  colorCache.set('hex', hash(hex), opacity, result);
  return result;
};

// Fast HSL color generation with caching
export const generateHSLColor = (scheme: string, factor: number, opacity: number): string => {
  const cached = colorCache.get(scheme, factor, opacity);
  if (cached) return cached;

  let hue: number;
  const saturation = 70;
  const lightness = 60;

  switch (scheme) {
    case 'centrality':
      // Blue to red gradient for centrality
      hue = factor < 0.5 
        ? 240 - (factor * 2 * 60)  // Blue to yellow
        : 60 - ((factor - 0.5) * 2 * 60); // Yellow to red
      break;
    case 'pagerank':
      // Purple to orange gradient
      hue = 280 - (factor * 250);
      break;
    case 'degree':
      // Green to red gradient
      hue = 120 - (factor * 120);
      break;
    case 'community':
      // Multi-hue community colors
      hue = (factor * 360) % 360;
      break;
    default:
      hue = 200; // Default blue
  }

  const result = `hsla(${Math.round(hue)}, ${saturation}%, ${lightness}%, ${opacity})`;
  colorCache.set(scheme, factor, opacity, result);
  return result;
};

// Interpolate between two colors
export const interpolateColor = (color1: string, color2: string, factor: number): string => {
  // Ensure factor is between 0 and 1
  factor = Math.max(0, Math.min(1, factor));
  
  // Cache key for interpolation
  const cacheKey = `interp:${hash(color1)}:${hash(color2)}:${Math.round(factor * 1000)}`;
  const cached = colorCache.get('interp', hash(cacheKey), 1);
  if (cached) return cached;
  
  // Remove # if present
  const c1 = color1.replace('#', '');
  const c2 = color2.replace('#', '');
  
  // Parse colors
  const r1 = parseInt(c1.substring(0, 2), 16);
  const g1 = parseInt(c1.substring(2, 4), 16);
  const b1 = parseInt(c1.substring(4, 6), 16);
  
  const r2 = parseInt(c2.substring(0, 2), 16);
  const g2 = parseInt(c2.substring(2, 4), 16);
  const b2 = parseInt(c2.substring(4, 6), 16);
  
  // Interpolate
  const r = Math.round(r1 + (r2 - r1) * factor);
  const g = Math.round(g1 + (g2 - g1) * factor);
  const b = Math.round(b1 + (b2 - b1) * factor);
  
  // Convert back to hex
  const toHex = (n: number) => n.toString(16).padStart(2, '0');
  const result = `#${toHex(r)}${toHex(g)}${toHex(b)}`;
  
  colorCache.set('interp', hash(cacheKey), 1, result);
  return result;
};

// Simple hash function for cache keys
function hash(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32-bit integer
  }
  return Math.abs(hash);
}

// Pre-compute color palettes for common schemes
export const generateColorPalette = (scheme: string, steps: number = 100): string[] => {
  const palette: string[] = [];
  for (let i = 0; i < steps; i++) {
    const factor = i / (steps - 1);
    palette.push(generateHSLColor(scheme, factor, 1));
  }
  return palette;
};