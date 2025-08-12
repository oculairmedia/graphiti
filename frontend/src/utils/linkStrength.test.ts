import { describe, it, expect } from 'vitest';

describe('Link Strength Configuration', () => {
  describe('Link Strength Calculation', () => {
    const calculateLinkStrength = (
      edgeType: string,
      config: {
        linkStrengthEnabled: boolean;
        entityEntityStrength: number;
        episodicStrength: number;
        defaultLinkStrength: number;
      }
    ) => {
      if (!config.linkStrengthEnabled) {
        return config.defaultLinkStrength;
      }
      
      if (edgeType === 'entity_entity' || edgeType === 'relates_to') {
        return config.entityEntityStrength;
      } else if (edgeType === 'episodic' || edgeType === 'temporal' || edgeType === 'mentioned_in') {
        return config.episodicStrength;
      }
      return config.defaultLinkStrength;
    };

    it('should return default strength when link strength is disabled', () => {
      const config = {
        linkStrengthEnabled: false,
        entityEntityStrength: 1.5,
        episodicStrength: 0.5,
        defaultLinkStrength: 1.0,
      };
      
      expect(calculateLinkStrength('entity_entity', config)).toBe(1.0);
      expect(calculateLinkStrength('episodic', config)).toBe(1.0);
      expect(calculateLinkStrength('unknown', config)).toBe(1.0);
    });

    it('should return entity strength for entity_entity links', () => {
      const config = {
        linkStrengthEnabled: true,
        entityEntityStrength: 1.5,
        episodicStrength: 0.5,
        defaultLinkStrength: 1.0,
      };
      
      expect(calculateLinkStrength('entity_entity', config)).toBe(1.5);
    });

    it('should return entity strength for relates_to links', () => {
      const config = {
        linkStrengthEnabled: true,
        entityEntityStrength: 1.5,
        episodicStrength: 0.5,
        defaultLinkStrength: 1.0,
      };
      
      expect(calculateLinkStrength('relates_to', config)).toBe(1.5);
    });

    it('should return episodic strength for episodic links', () => {
      const config = {
        linkStrengthEnabled: true,
        entityEntityStrength: 1.5,
        episodicStrength: 0.5,
        defaultLinkStrength: 1.0,
      };
      
      expect(calculateLinkStrength('episodic', config)).toBe(0.5);
    });

    it('should return episodic strength for temporal links', () => {
      const config = {
        linkStrengthEnabled: true,
        entityEntityStrength: 1.5,
        episodicStrength: 0.5,
        defaultLinkStrength: 1.0,
      };
      
      expect(calculateLinkStrength('temporal', config)).toBe(0.5);
    });

    it('should return episodic strength for mentioned_in links', () => {
      const config = {
        linkStrengthEnabled: true,
        entityEntityStrength: 1.5,
        episodicStrength: 0.5,
        defaultLinkStrength: 1.0,
      };
      
      expect(calculateLinkStrength('mentioned_in', config)).toBe(0.5);
    });

    it('should return default strength for unknown link types', () => {
      const config = {
        linkStrengthEnabled: true,
        entityEntityStrength: 1.5,
        episodicStrength: 0.5,
        defaultLinkStrength: 1.0,
      };
      
      expect(calculateLinkStrength('custom_type', config)).toBe(1.0);
      expect(calculateLinkStrength('', config)).toBe(1.0);
      expect(calculateLinkStrength('default', config)).toBe(1.0);
    });
  });

  describe('Link Animation Configuration', () => {
    const calculateAnimatedStrength = (
      baseStrength: number,
      animationConfig: {
        linkAnimationEnabled: boolean;
        linkAnimationAmplitude: number;
        linkAnimationFrequency: number;
      },
      time: number
    ) => {
      if (!animationConfig.linkAnimationEnabled) {
        return baseStrength;
      }
      
      // Simple sine wave animation
      const variation = Math.sin(time * animationConfig.linkAnimationFrequency) * 
                       animationConfig.linkAnimationAmplitude;
      return baseStrength * (1 + variation);
    };

    it('should return base strength when animation is disabled', () => {
      const config = {
        linkAnimationEnabled: false,
        linkAnimationAmplitude: 0.2,
        linkAnimationFrequency: 0.001,
      };
      
      expect(calculateAnimatedStrength(1.0, config, 0)).toBe(1.0);
      expect(calculateAnimatedStrength(1.5, config, 1000)).toBe(1.5);
    });

    it('should apply sine wave animation when enabled', () => {
      const config = {
        linkAnimationEnabled: true,
        linkAnimationAmplitude: 0.2,
        linkAnimationFrequency: Math.PI / 1000, // Complete cycle every 2000ms
      };
      
      // At time 0, sin(0) = 0, so strength = base * (1 + 0) = base
      expect(calculateAnimatedStrength(1.0, config, 0)).toBeCloseTo(1.0);
      
      // At time 500, sin(π/2) = 1, so strength = base * (1 + 0.2) = base * 1.2
      expect(calculateAnimatedStrength(1.0, config, 500)).toBeCloseTo(1.2);
      
      // At time 1000, sin(π) = 0, so strength = base * (1 + 0) = base
      expect(calculateAnimatedStrength(1.0, config, 1000)).toBeCloseTo(1.0);
      
      // At time 1500, sin(3π/2) = -1, so strength = base * (1 - 0.2) = base * 0.8
      expect(calculateAnimatedStrength(1.0, config, 1500)).toBeCloseTo(0.8);
    });

    it('should scale animation with different amplitudes', () => {
      const config = {
        linkAnimationEnabled: true,
        linkAnimationAmplitude: 0.5, // ±50% variation
        linkAnimationFrequency: Math.PI / 1000,
      };
      
      // At peak (sin = 1), strength = base * (1 + 0.5) = base * 1.5
      expect(calculateAnimatedStrength(1.0, config, 500)).toBeCloseTo(1.5);
      
      // At trough (sin = -1), strength = base * (1 - 0.5) = base * 0.5
      expect(calculateAnimatedStrength(1.0, config, 1500)).toBeCloseTo(0.5);
    });

    it('should work with different base strengths', () => {
      const config = {
        linkAnimationEnabled: true,
        linkAnimationAmplitude: 0.2,
        linkAnimationFrequency: Math.PI / 1000,
      };
      
      // Entity links (base strength 1.5)
      expect(calculateAnimatedStrength(1.5, config, 500)).toBeCloseTo(1.8); // 1.5 * 1.2
      
      // Episodic links (base strength 0.5)
      expect(calculateAnimatedStrength(0.5, config, 500)).toBeCloseTo(0.6); // 0.5 * 1.2
    });
  });

  describe('Combined Link Strength with Animation', () => {
    it('should combine type-based strength with animation', () => {
      const config = {
        linkStrengthEnabled: true,
        entityEntityStrength: 1.5,
        episodicStrength: 0.5,
        defaultLinkStrength: 1.0,
        linkAnimationEnabled: true,
        linkAnimationAmplitude: 0.2,
        linkAnimationFrequency: Math.PI / 1000,
      };
      
      // Entity link at peak animation
      const entityStrength = 1.5 * (1 + 0.2); // 1.8
      expect(entityStrength).toBeCloseTo(1.8);
      
      // Episodic link at peak animation
      const episodicStrength = 0.5 * (1 + 0.2); // 0.6
      expect(episodicStrength).toBeCloseTo(0.6);
      
      // Default link at trough animation
      const defaultStrength = 1.0 * (1 - 0.2); // 0.8
      expect(defaultStrength).toBeCloseTo(0.8);
    });
  });
});