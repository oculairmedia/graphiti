import React from 'react';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

interface ControlSliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (value: number) => void;
  className?: string;
  showInput?: boolean;
  formatValue?: (value: number) => string;
  icon?: React.ReactNode;
}

export const ControlSlider: React.FC<ControlSliderProps> = ({
  label,
  value,
  min,
  max,
  step = 0.01,
  onChange,
  className,
  showInput = true,
  formatValue,
  icon,
}) => {
  const handleSliderChange = (values: number[]) => {
    onChange(values[0]);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = parseFloat(e.target.value);
    if (!isNaN(newValue)) {
      onChange(Math.max(min, Math.min(max, newValue)));
    }
  };

  const displayValue = formatValue ? formatValue(value) : value.toFixed(2);

  return (
    <div className={cn('space-y-2', className)}>
      <div className="flex items-center justify-between">
        <Label className="text-xs font-medium flex items-center gap-1.5">
          {icon}
          {label}
        </Label>
        {showInput && (
          <Input
            type="number"
            value={value}
            onChange={handleInputChange}
            min={min}
            max={max}
            step={step}
            className="w-20 h-7 text-xs text-right"
          />
        )}
        {!showInput && (
          <span className="text-xs text-muted-foreground">{displayValue}</span>
        )}
      </div>
      <Slider
        value={[value]}
        onValueChange={handleSliderChange}
        min={min}
        max={max}
        step={step}
        className="w-full"
      />
    </div>
  );
};