import React, { useState, useEffect } from 'react';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { useDebouncedCallback } from '@/hooks/useDebouncedCallback';

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
  disabled?: boolean;
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
  disabled,
}) => {
  // Handle undefined or null values by using the minimum value
  const safeValue = value ?? min;
  
  // Local state for immediate visual feedback; debounce the parent onChange
  const [localValue, setLocalValue] = useState(safeValue);
  useEffect(() => { setLocalValue(safeValue); }, [safeValue]);
  const debouncedOnChange = useDebouncedCallback(onChange, 150);
  
  const handleSliderChange = (values: number[]) => {
    setLocalValue(values[0]);
    debouncedOnChange(values[0]);
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = parseFloat(e.target.value);
    if (!isNaN(newValue)) {
      const clamped = Math.max(min, Math.min(max, newValue));
      setLocalValue(clamped);
      debouncedOnChange(clamped);
    }
  };

  const displayValue = formatValue ? formatValue(localValue) : localValue.toFixed(2);

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
            value={localValue}
            onChange={handleInputChange}
            min={min}
            max={max}
            step={step}
            className="w-20 h-7 text-xs text-right"
            disabled={disabled}
          />
        )}
        {!showInput && (
          <span className="text-xs text-muted-foreground">{displayValue}</span>
        )}
      </div>
      <Slider
        value={[localValue]}
        onValueChange={handleSliderChange}
        min={min}
        max={max}
        step={step}
        className="w-full"
        disabled={disabled}
      />
    </div>
  );
};