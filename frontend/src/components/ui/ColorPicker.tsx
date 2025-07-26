import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Palette, Check } from 'lucide-react';

interface ColorPickerProps {
  color: string;
  onChange: (color: string) => void;
  label?: string;
  swatches?: string[];
  className?: string;
}

const DEFAULT_PRESETS = [
  '#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD',
  '#98D8C8', '#F7DC6F', '#BB8FCE', '#85C1E9', '#F8C471', '#82E0AA',
  '#ffffff', '#f8f9fa', '#e9ecef', '#dee2e6', '#ced4da', '#adb5bd',
  '#6c757d', '#495057', '#343a40', '#212529', '#000000', '#dc3545',
  '#fd7e14', '#ffc107', '#28a745', '#20c997', '#17a2b8', '#6f42c1',
  '#e83e8c', '#6610f2', '#007bff', '#28a745'
];

export const ColorPicker: React.FC<ColorPickerProps> = ({
  color,
  onChange,
  label,
  swatches = DEFAULT_PRESETS,
  className = ""
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [customColor, setCustomColor] = useState(color || '#000000');

  const handlePresetClick = (color: string) => {
    onChange(color);
    setCustomColor(color);
    setIsOpen(false);
  };

  const handleCustomChange = (color: string) => {
    setCustomColor(color);
    onChange(color);
  };

  return (
    <div className={`space-y-2 ${className}`}>
      {label && (
        <Label className="text-xs text-muted-foreground">{label}</Label>
      )}
      
      <Popover open={isOpen} onOpenChange={setIsOpen}>
        <PopoverTrigger asChild>
          <Button
            variant="outline"
            className="w-full h-10 justify-start gap-2 hover:bg-secondary/80"
          >
            <div
              className="w-5 h-5 rounded-full border-2 border-border/50 shadow-sm"
              style={{ backgroundColor: color || '#000000' }}
            />
            <span className="flex-1 text-left text-sm font-mono">
              {(color || '#000000').toUpperCase()}
            </span>
            <Palette className="h-4 w-4 text-muted-foreground" />
          </Button>
        </PopoverTrigger>
        
        <PopoverContent className="w-80 p-4 glass" align="start">
          <div className="space-y-4">
            {/* Custom Color Input */}
            <div className="space-y-2">
              <Label className="text-xs font-medium">Custom Color</Label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Input
                    type="text"
                    value={customColor}
                    onChange={(e) => handleCustomChange(e.target.value)}
                    placeholder="#000000"
                    className="h-9 font-mono text-sm pr-10"
                  />
                  <div
                    className="absolute right-2 top-1/2 -translate-y-1/2 w-5 h-5 rounded border border-border/50"
                    style={{ backgroundColor: customColor }}
                  />
                </div>
                <Input
                  type="color"
                  value={customColor}
                  onChange={(e) => handleCustomChange(e.target.value)}
                  className="w-12 h-9 p-1 border-2 cursor-pointer"
                />
              </div>
            </div>

            {/* Preset Colors */}
            <div className="space-y-2">
              <Label className="text-xs font-medium">Preset Colors</Label>
              <div className="grid grid-cols-8 gap-2">
                {swatches.map((swatchColor, i) => (
                  <button
                    key={i}
                    onClick={() => handlePresetClick(swatchColor)}
                    className="group relative w-8 h-8 rounded-lg border-2 border-border/30 hover:border-primary/50 hover:scale-110 transition-all duration-200 shadow-sm hover:shadow-md"
                    style={{ backgroundColor: swatchColor }}
                    title={swatchColor}
                  >
                    {(color || '#000000').toLowerCase() === swatchColor.toLowerCase() && (
                      <Check className="h-3 w-3 text-white absolute inset-0 m-auto drop-shadow-lg" />
                    )}
                  </button>
                ))}
              </div>
            </div>

            {/* Current Selection */}
            <div className="pt-2 border-t border-border/20">
              <div className="flex items-center justify-between">
                <Label className="text-xs text-muted-foreground">Selected</Label>
                <Badge variant="secondary" className="font-mono text-xs">
                  {(color || '#000000').toUpperCase()}
                </Badge>
              </div>
            </div>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
};

export default ColorPicker;