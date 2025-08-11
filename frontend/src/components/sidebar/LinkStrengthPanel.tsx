import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Label } from '../ui/label';
import { Slider } from '../ui/slider';
import { Switch } from '../ui/switch';
import { useGraphConfig } from '../../contexts/GraphConfigProvider';
import { useTheme } from '../theme/ThemeContext';

export function LinkStrengthPanel() {
  const { config, updateConfig } = useGraphConfig();
  const { theme } = useTheme();

  const handleEnabledChange = (checked: boolean) => {
    updateConfig({ linkStrengthEnabled: checked });
  };

  const handleEntityStrengthChange = (value: number[]) => {
    updateConfig({ entityEntityStrength: value[0] });
  };

  const handleEpisodicStrengthChange = (value: number[]) => {
    updateConfig({ episodicStrength: value[0] });
  };

  const handleDefaultStrengthChange = (value: number[]) => {
    updateConfig({ defaultLinkStrength: value[0] });
  };

  return (
    <Card className="mb-4">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium flex items-center justify-between">
          Link Strength
          <Switch
            checked={config.linkStrengthEnabled}
            onCheckedChange={handleEnabledChange}
            className="data-[state=checked]:bg-green-500"
          />
        </CardTitle>
      </CardHeader>
      
      {config.linkStrengthEnabled && (
        <CardContent className="space-y-4">
          {/* Entity-Entity Strength */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs">Entity-Entity Links</Label>
              <span className="text-xs text-muted-foreground">
                {config.entityEntityStrength.toFixed(1)}x
              </span>
            </div>
            <Slider
              value={[config.entityEntityStrength]}
              onValueChange={handleEntityStrengthChange}
              min={0.1}
              max={3.0}
              step={0.1}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Stronger connections between entities (tighter clustering)
            </p>
          </div>

          {/* Episodic Strength */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs">Episodic/Temporal Links</Label>
              <span className="text-xs text-muted-foreground">
                {config.episodicStrength.toFixed(1)}x
              </span>
            </div>
            <Slider
              value={[config.episodicStrength]}
              onValueChange={handleEpisodicStrengthChange}
              min={0.1}
              max={3.0}
              step={0.1}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Weaker connections for temporal relationships
            </p>
          </div>

          {/* Default Strength */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs">Other Links</Label>
              <span className="text-xs text-muted-foreground">
                {config.defaultLinkStrength.toFixed(1)}x
              </span>
            </div>
            <Slider
              value={[config.defaultLinkStrength]}
              onValueChange={handleDefaultStrengthChange}
              min={0.1}
              max={3.0}
              step={0.1}
              className="w-full"
            />
            <p className="text-xs text-muted-foreground">
              Default strength for unspecified link types
            </p>
          </div>

          {/* Reset button */}
          <button
            onClick={() => {
              updateConfig({
                entityEntityStrength: 1.5,
                episodicStrength: 0.5,
                defaultLinkStrength: 1.0,
              });
            }}
            className="w-full px-3 py-1 text-xs bg-secondary hover:bg-secondary/80 rounded-md transition-colors"
          >
            Reset to Defaults
          </button>
        </CardContent>
      )}
    </Card>
  );
}