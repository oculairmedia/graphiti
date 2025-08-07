import React from 'react';
import { Settings2, Eye, Tag, MousePointer, MoreHorizontal } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { ColorPicker } from '@/components/ui/ColorPicker';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { ControlSlider } from '@/components/ui/ControlSlider';
import { ControlGroup } from '@/components/ui/ControlGroup';

interface RenderControlsTabProps {
  config: {
    linkWidth: number;
    linkWidthBy: string;
    linkOpacity: number;
    linkColor: string;
    backgroundColor: string;
    linkColorScheme: string;
    hoveredPointCursor: string;
    renderHoveredPointRing: boolean;
    hoveredPointRingColor: string;
    focusedPointRingColor: string;
    renderLabels: boolean;
    showDynamicLabels: boolean;
    showTopLabels: boolean;
    showTopLabelsLimit: number;
    labelBy: string;
    labelVisibilityThreshold: number;
    labelSize: number;
    labelFontWeight: number;
    labelColor: string;
    labelBackgroundColor: string;
    hoveredLabelSize: number;
    hoveredLabelFontWeight: number;
    hoveredLabelColor: string;
    hoveredLabelBackgroundColor: string;
    pixelationThreshold: number;
    renderSelectedNodesOnTop: boolean;
    advancedOptionsEnabled: boolean;
    edgeArrows: boolean;
    edgeArrowScale: number;
    pointsOnEdge: boolean;
    curvedLinks: boolean;
    curvedLinkSegments: number;
    curvedLinkWeight: number;
    curvedLinkControlPointDistance: number;
  };
  onConfigUpdate: (updates: Record<string, unknown>) => void;
}

export const RenderControlsTab: React.FC<RenderControlsTabProps> = ({
  config,
  onConfigUpdate,
}) => {
  return (
    <div className="space-y-4">
      {/* Link & Background */}
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <Settings2 className="h-4 w-4 text-primary" />
            <span>Link & Background</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <ControlSlider
            label="Link Width"
            value={config.linkWidth}
            min={0.1}
            max={5}
            step={0.1}
            onChange={(value) => onConfigUpdate({ linkWidth: value })}
            formatValue={(v) => v.toFixed(1)}
          />

          <div>
            <Label className="text-xs text-muted-foreground">Link Width Column</Label>
            <Input
              value={config.linkWidthBy}
              onChange={(e) => onConfigUpdate({ linkWidthBy: e.target.value })}
              className="h-8 bg-secondary/30 mt-1"
              placeholder="weight"
            />
            <p className="text-xs text-muted-foreground mt-1">Column name for link width values</p>
          </div>

          <ControlSlider
            label="Link Opacity"
            value={config.linkOpacity * 100}
            min={0}
            max={100}
            step={5}
            onChange={(value) => onConfigUpdate({ linkOpacity: value / 100 })}
            formatValue={(v) => `${Math.round(v)}%`}
          />

          <ColorPicker
            color={config.linkColor}
            onChange={(color) => onConfigUpdate({ linkColor: color })}
            label="Link Color"
            swatches={[
              '#666666', '#ffffff', '#ff6b6b', '#4ecdc4', '#45b7d1',
              '#96ceb4', '#ffeaa7', '#dda0dd', '#98d8c8', '#f7dc6f',
              '#bb8fce', '#85c1e9', '#f8c471', '#82e0aa', '#adb5bd',
              '#495057'
            ]}
          />

          <ColorPicker
            color={config.backgroundColor}
            onChange={(color) => onConfigUpdate({ backgroundColor: color })}
            label="Background Color"
            swatches={[
              '#000000', '#0a0a0a', '#1a1a1a', '#2d3748', '#1a202c',
              '#2a2a2a', '#0f172a', '#111827', '#1f2937', '#374151',
              '#ffffff', '#f8f9fa', '#e9ecef', '#dee2e6'
            ]}
          />

          <div>
            <Label className="text-xs text-muted-foreground">Link Color Scheme</Label>
            <Select 
              value={config.linkColorScheme} 
              onValueChange={(value) => onConfigUpdate({ linkColorScheme: value })}
            >
              <SelectTrigger className="h-8 bg-secondary/30">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="glass">
                <SelectItem value="uniform">➖ Uniform Color</SelectItem>
                <SelectItem value="by-weight">⚖️ By Edge Weight</SelectItem>
                <SelectItem value="by-type">🔗 By Edge Type</SelectItem>
                <SelectItem value="by-distance">📏 By Distance</SelectItem>
                <SelectItem value="gradient">🌈 Node Color Gradient</SelectItem>
                <SelectItem value="by-community">👥 By Community Bridge</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center justify-between">
            <Label className="text-xs text-muted-foreground">Curved Links</Label>
            <Checkbox
              checked={config.curvedLinks}
              onCheckedChange={(checked) => onConfigUpdate({ curvedLinks: !!checked })}
            />
          </div>

          {config.curvedLinks && (
            <>
              <ControlSlider
                label="Curve Segments"
                value={config.curvedLinkSegments}
                min={3}
                max={50}
                step={1}
                onChange={(value) => onConfigUpdate({ curvedLinkSegments: value })}
                formatValue={(v) => v.toString()}
              />
              <p className="text-xs text-muted-foreground -mt-2">Number of segments for curved links</p>

              <ControlSlider
                label="Curve Weight"
                value={config.curvedLinkWeight}
                min={0}
                max={2}
                step={0.1}
                onChange={(value) => onConfigUpdate({ curvedLinkWeight: value })}
                formatValue={(v) => v.toFixed(1)}
              />
              <p className="text-xs text-muted-foreground -mt-2">Strength of the curve effect</p>

              <ControlSlider
                label="Control Point Distance"
                value={config.curvedLinkControlPointDistance}
                min={0}
                max={2}
                step={0.1}
                onChange={(value) => onConfigUpdate({ curvedLinkControlPointDistance: value })}
                formatValue={(v) => v.toFixed(1)}
              />
              <p className="text-xs text-muted-foreground -mt-2">Distance of curve control points</p>
            </>
          )}
        </CardContent>
      </Card>

      {/* Hover & Focus Effects */}
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <Eye className="h-4 w-4 text-primary" />
            <span>Hover & Focus Effects</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label className="text-xs text-muted-foreground">Hover Cursor</Label>
            <Select value={config.hoveredPointCursor} onValueChange={(value) => onConfigUpdate({ hoveredPointCursor: value })}>
              <SelectTrigger className="h-8 bg-secondary/30">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="glass">
                <SelectItem value="auto">↗️ Auto</SelectItem>
                <SelectItem value="pointer">👆 Pointer</SelectItem>
                <SelectItem value="crosshair">✛ Crosshair</SelectItem>
                <SelectItem value="grab">✋ Grab</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center justify-between">
            <Label className="text-xs text-muted-foreground">Show Hover Ring</Label>
            <Checkbox
              checked={config.renderHoveredPointRing}
              onCheckedChange={(checked) => onConfigUpdate({ renderHoveredPointRing: !!checked })}
            />
          </div>

          {config.renderHoveredPointRing && (
            <ColorPicker
              color={config.hoveredPointRingColor}
              onChange={(color) => onConfigUpdate({ hoveredPointRingColor: color })}
              label="Hover Ring Color"
              swatches={[
                '#22d3ee', '#06b6d4', '#0891b2', '#0e7490',
                '#fbbf24', '#f59e0b', '#d97706', '#b45309',
                '#ef4444', '#dc2626', '#b91c1c', '#991b1b',
                '#10b981', '#059669', '#047857', '#065f46'
              ]}
            />
          )}

          <ColorPicker
            color={config.focusedPointRingColor}
            onChange={(color) => onConfigUpdate({ focusedPointRingColor: color })}
            label="Focus Ring Color"
            swatches={[
              '#ff0055', '#ff006e', '#c9184a', '#a40e4c',
              '#7f1d1d', '#dc2626', '#b91c1c', '#991b1b',
              '#ffaa00', '#ff8c00', '#ff6b00', '#ff4500'
            ]}
          />
        </CardContent>
      </Card>

      {/* Label Settings */}
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <Tag className="h-4 w-4 text-primary" />
            <span>Label Settings</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label className="text-xs text-muted-foreground">Render Labels</Label>
            <Checkbox
              checked={config.renderLabels}
              onCheckedChange={(checked) => onConfigUpdate({ renderLabels: !!checked })}
            />
          </div>

          {config.renderLabels && (
            <>
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="text-xs text-muted-foreground">Dynamic Labels</Label>
                  <Checkbox
                    checked={config.showDynamicLabels}
                    onCheckedChange={(checked) => onConfigUpdate({ showDynamicLabels: !!checked })}
                  />
                </div>
                
                <div className="flex items-center justify-between">
                  <Label className="text-xs text-muted-foreground">Top Labels</Label>
                  <Checkbox
                    checked={config.showTopLabels}
                    onCheckedChange={(checked) => onConfigUpdate({ showTopLabels: !!checked })}
                  />
                </div>
                
                {config.showTopLabels && (
                  <ControlSlider
                    label="Max Labels"
                    value={config.showTopLabelsLimit}
                    min={10}
                    max={500}
                    step={10}
                    onChange={(value) => onConfigUpdate({ showTopLabelsLimit: value })}
                    formatValue={(v) => `${v} labels`}
                  />
                )}
              </div>

              <div>
                <Label className="text-xs text-muted-foreground">Label By</Label>
                <Input
                  value={config.labelBy}
                  onChange={(e) => onConfigUpdate({ labelBy: e.target.value })}
                  className="h-8 bg-secondary/30 mt-1"
                  placeholder="label"
                />
              </div>

              <ControlSlider
                label="Label Visibility Threshold"
                value={config.labelVisibilityThreshold}
                min={0}
                max={1}
                step={0.01}
                onChange={(value) => onConfigUpdate({ labelVisibilityThreshold: value })}
              />

              <ControlGroup title="Default Labels" variant="plain">
                <ControlSlider
                  label="Size"
                  value={config.labelSize}
                  min={8}
                  max={24}
                  step={1}
                  onChange={(value) => onConfigUpdate({ labelSize: value })}
                  formatValue={(v) => `${v}px`}
                />
                <ControlSlider
                  label="Font Weight"
                  value={config.labelFontWeight}
                  min={100}
                  max={900}
                  step={100}
                  onChange={(value) => onConfigUpdate({ labelFontWeight: value })}
                  formatValue={(v) => v.toString()}
                />
                <ColorPicker
                  color={config.labelColor}
                  onChange={(color) => onConfigUpdate({ labelColor: color })}
                  label="Text Color"
                />
                <ColorPicker
                  color={config.labelBackgroundColor}
                  onChange={(color) => onConfigUpdate({ labelBackgroundColor: color })}
                  label="Background Color"
                />
              </ControlGroup>

              <ControlGroup title="Hovered Labels" variant="plain">
                <ControlSlider
                  label="Size"
                  value={config.hoveredLabelSize}
                  min={8}
                  max={32}
                  step={1}
                  onChange={(value) => onConfigUpdate({ hoveredLabelSize: value })}
                  formatValue={(v) => `${v}px`}
                />
                <ControlSlider
                  label="Font Weight"
                  value={config.hoveredLabelFontWeight}
                  min={100}
                  max={900}
                  step={100}
                  onChange={(value) => onConfigUpdate({ hoveredLabelFontWeight: value })}
                  formatValue={(v) => v.toString()}
                />
                <ColorPicker
                  color={config.hoveredLabelColor}
                  onChange={(color) => onConfigUpdate({ hoveredLabelColor: color })}
                  label="Text Color"
                />
                <ColorPicker
                  color={config.hoveredLabelBackgroundColor}
                  onChange={(color) => onConfigUpdate({ hoveredLabelBackgroundColor: color })}
                  label="Background Color"
                />
              </ControlGroup>
            </>
          )}
        </CardContent>
      </Card>

      {/* Advanced Options */}
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <MoreHorizontal className="h-4 w-4 text-primary" />
            <span>Advanced Options</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <Label className="text-xs text-muted-foreground">Enable Advanced Options</Label>
            <Checkbox
              checked={config.advancedOptionsEnabled}
              onCheckedChange={(checked) => onConfigUpdate({ advancedOptionsEnabled: !!checked })}
            />
          </div>

          {config.advancedOptionsEnabled && (
            <>
              <ControlSlider
                label="Pixelation Threshold"
                value={config.pixelationThreshold}
                min={0}
                max={20}
                step={1}
                onChange={(value) => onConfigUpdate({ pixelationThreshold: value })}
                formatValue={(v) => v.toString()}
              />

              <div className="flex items-center justify-between">
                <Label className="text-xs text-muted-foreground">Render Selected on Top</Label>
                <Checkbox
                  checked={config.renderSelectedNodesOnTop}
                  onCheckedChange={(checked) => onConfigUpdate({ renderSelectedNodesOnTop: !!checked })}
                />
              </div>

              <div className="flex items-center justify-between">
                <Label className="text-xs text-muted-foreground">Edge Arrows</Label>
                <Checkbox
                  checked={config.edgeArrows}
                  onCheckedChange={(checked) => onConfigUpdate({ edgeArrows: !!checked })}
                />
              </div>

              {config.edgeArrows && (
                <ControlSlider
                  label="Arrow Scale"
                  value={config.edgeArrowScale}
                  min={0.5}
                  max={3}
                  step={0.1}
                  onChange={(value) => onConfigUpdate({ edgeArrowScale: value })}
                  formatValue={(v) => `${v.toFixed(1)}x`}
                />
              )}

              <div className="flex items-center justify-between">
                <Label className="text-xs text-muted-foreground">Points on Edge</Label>
                <Checkbox
                  checked={config.pointsOnEdge}
                  onCheckedChange={(checked) => onConfigUpdate({ pointsOnEdge: !!checked })}
                />
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
};