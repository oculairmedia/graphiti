import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';

interface ControlGroupProps {
  title?: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  variant?: 'card' | 'section' | 'plain';
  collapsible?: boolean;
  defaultExpanded?: boolean;
}

export const ControlGroup: React.FC<ControlGroupProps> = ({
  title,
  icon,
  children,
  className,
  variant = 'section',
  collapsible = false,
  defaultExpanded = true,
}) => {
  const [isExpanded, setIsExpanded] = React.useState(defaultExpanded);

  if (variant === 'card') {
    return (
      <Card className={cn('shadow-sm', className)}>
        {title && (
          <CardHeader 
            className={cn(
              'py-3 px-4',
              collapsible && 'cursor-pointer hover:bg-muted/50 transition-colors'
            )}
            onClick={collapsible ? () => setIsExpanded(!isExpanded) : undefined}
          >
            <CardTitle className="text-sm font-medium flex items-center justify-between">
              <span className="flex items-center gap-2">
                {icon}
                {title}
              </span>
              {collapsible && (
                <span className={cn(
                  'text-muted-foreground transition-transform',
                  !isExpanded && 'rotate-180'
                )}>
                  ▲
                </span>
              )}
            </CardTitle>
          </CardHeader>
        )}
        {(!collapsible || isExpanded) && (
          <CardContent className="py-3 px-4 space-y-3">
            {children}
          </CardContent>
        )}
      </Card>
    );
  }

  if (variant === 'section') {
    return (
      <div className={cn('space-y-3', className)}>
        {title && (
          <>
            <div 
              className={cn(
                'flex items-center justify-between',
                collapsible && 'cursor-pointer hover:opacity-80 transition-opacity'
              )}
              onClick={collapsible ? () => setIsExpanded(!isExpanded) : undefined}
            >
              <h3 className="text-sm font-medium flex items-center gap-2">
                {icon}
                {title}
              </h3>
              {collapsible && (
                <span className={cn(
                  'text-muted-foreground text-xs transition-transform',
                  !isExpanded && 'rotate-180'
                )}>
                  ▲
                </span>
              )}
            </div>
            <Separator className="my-2" />
          </>
        )}
        {(!collapsible || isExpanded) && (
          <div className="space-y-3">
            {children}
          </div>
        )}
      </div>
    );
  }

  // Plain variant
  return (
    <div className={cn('space-y-3', className)}>
      {children}
    </div>
  );
};