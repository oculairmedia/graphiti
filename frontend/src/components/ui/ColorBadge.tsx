import React from 'react';
import { Badge } from '@/components/ui/badge';
import { useColorUtils } from '@/hooks/useColorUtils';
import { cn } from '@/lib/utils';

interface ColorBadgeProps {
  color: string;
  label: string;
  size?: 'sm' | 'md' | 'lg';
  variant?: 'default' | 'outline' | 'secondary';
  className?: string;
  onClick?: () => void;
}

export const ColorBadge: React.FC<ColorBadgeProps> = ({
  color,
  label,
  size = 'md',
  variant = 'outline',
  className,
  onClick,
}) => {
  const { hexToHsl, getContrastingTextColor } = useColorUtils();
  
  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-2.5 py-0.5',
    lg: 'text-base px-3 py-1',
  };

  const hslColor = hexToHsl(color);
  const textColor = getContrastingTextColor(color);

  return (
    <Badge
      variant={variant}
      className={cn(
        sizeClasses[size],
        'relative overflow-hidden cursor-pointer transition-all',
        onClick && 'hover:scale-105',
        className
      )}
      onClick={onClick}
      style={{
        '--indicator-color': hslColor,
        color: variant === 'default' ? textColor : undefined,
        backgroundColor: variant === 'default' ? color : undefined,
      } as React.CSSProperties}
    >
      {variant === 'outline' && (
        <span
          className="inline-block w-2 h-2 rounded-full mr-1.5"
          style={{ backgroundColor: `hsl(${hslColor})` }}
        />
      )}
      <span className={cn(
        'relative z-10',
        variant === 'default' && 'font-medium'
      )}>
        {label}
      </span>
      {variant === 'secondary' && (
        <div
          className="absolute inset-0 opacity-10"
          style={{ backgroundColor: color }}
        />
      )}
    </Badge>
  );
};