import React from 'react';
import { Settings, Monitor, Mouse, Keyboard, Info, Activity } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { useQueueStatus } from '@/hooks/useQueueStatus';

interface SettingsTabProps {
  config: {
    showFPS: boolean;
    showNodeCount: boolean;
    enableHoverEffects: boolean;
    enablePanOnDrag: boolean;
    enableZoomOnScroll: boolean;
    enableClickSelection: boolean;
    enableDoubleClickFocus: boolean;
    enableKeyboardShortcuts: boolean;
    showDebugInfo: boolean;
    performanceMode: boolean;
    followSelectedNode?: boolean;
  };
  onConfigUpdate: (updates: Record<string, unknown>) => void;
  graphStats?: {
    nodeCount: number;
    edgeCount: number;
  };
}

export const SettingsTab: React.FC<SettingsTabProps> = ({
  config,
  onConfigUpdate,
  graphStats,
}) => {
  const { queueStatus, isLoading: queueLoading, error: queueError } = useQueueStatus();
  return (
    <div className="space-y-4">
      {/* Display Settings */}
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <Monitor className="h-4 w-4 text-primary" />
            <span>Display Settings</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between">
            <Label className="text-sm">Show FPS Counter</Label>
            <Checkbox
              checked={config.showFPS}
              onCheckedChange={(checked) => onConfigUpdate({ showFPS: !!checked })}
            />
          </div>
          <div className="flex items-center justify-between">
            <Label className="text-sm">Show Node Count</Label>
            <Checkbox
              checked={config.showNodeCount}
              onCheckedChange={(checked) => onConfigUpdate({ showNodeCount: !!checked })}
            />
          </div>
          <div className="flex items-center justify-between">
            <Label className="text-sm">Show Debug Info</Label>
            <Checkbox
              checked={config.showDebugInfo}
              onCheckedChange={(checked) => onConfigUpdate({ showDebugInfo: !!checked })}
            />
          </div>
        </CardContent>
      </Card>

      {/* Interaction Settings */}
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <Mouse className="h-4 w-4 text-primary" />
            <span>Interaction Settings</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between">
            <Label className="text-sm">Enable Hover Effects</Label>
            <Checkbox
              checked={config.enableHoverEffects}
              onCheckedChange={(checked) => onConfigUpdate({ enableHoverEffects: !!checked })}
            />
          </div>
          <div className="flex items-center justify-between">
            <Label className="text-sm">Pan on Drag</Label>
            <Checkbox
              checked={config.enablePanOnDrag}
              onCheckedChange={(checked) => onConfigUpdate({ enablePanOnDrag: !!checked })}
            />
          </div>
          <div className="flex items-center justify-between">
            <Label className="text-sm">Zoom on Scroll</Label>
            <Checkbox
              checked={config.enableZoomOnScroll}
              onCheckedChange={(checked) => onConfigUpdate({ enableZoomOnScroll: !!checked })}
            />
          </div>
          <div className="flex items-center justify-between">
            <Label className="text-sm">Click to Select</Label>
            <Checkbox
              checked={config.enableClickSelection}
              onCheckedChange={(checked) => onConfigUpdate({ enableClickSelection: !!checked })}
            />
          </div>
          <div className="flex items-center justify-between">
            <Label className="text-sm">Double-click to Focus</Label>
            <Checkbox
              checked={config.enableDoubleClickFocus}
              onCheckedChange={(checked) => onConfigUpdate({ enableDoubleClickFocus: !!checked })}
            />
          </div>
          <Separator className="my-2" />
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <Label className="text-sm">Follow Selected Node</Label>
              <p className="text-xs text-muted-foreground">Camera follows node during simulation</p>
            </div>
            <Checkbox
              checked={config.followSelectedNode ?? false}
              onCheckedChange={(checked) => onConfigUpdate({ followSelectedNode: !!checked })}
            />
          </div>
        </CardContent>
      </Card>

      {/* Keyboard Shortcuts */}
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <Keyboard className="h-4 w-4 text-primary" />
            <span>Keyboard Shortcuts</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between mb-3">
            <Label className="text-sm">Enable Shortcuts</Label>
            <Checkbox
              checked={config.enableKeyboardShortcuts}
              onCheckedChange={(checked) => onConfigUpdate({ enableKeyboardShortcuts: !!checked })}
            />
          </div>
          
          {config.enableKeyboardShortcuts && (
            <>
              <Separator />
              <div className="space-y-2 text-xs text-muted-foreground">
                <div className="flex justify-between">
                  <span>Fit View</span>
                  <Badge variant="secondary" className="text-xs">F</Badge>
                </div>
                <div className="flex justify-between">
                  <span>Zoom In/Out</span>
                  <div className="space-x-1">
                    <Badge variant="secondary" className="text-xs">+</Badge>
                    <Badge variant="secondary" className="text-xs">-</Badge>
                  </div>
                </div>
                <div className="flex justify-between">
                  <span>Pan</span>
                  <Badge variant="secondary" className="text-xs">Arrow Keys</Badge>
                </div>
                <div className="flex justify-between">
                  <span>Select All</span>
                  <Badge variant="secondary" className="text-xs">Ctrl+A</Badge>
                </div>
                <div className="flex justify-between">
                  <span>Deselect All</span>
                  <Badge variant="secondary" className="text-xs">Esc</Badge>
                </div>
                <div className="flex justify-between">
                  <span>Toggle Physics</span>
                  <Badge variant="secondary" className="text-xs">Space</Badge>
                </div>
                <div className="flex justify-between">
                  <span>Toggle Labels</span>
                  <Badge variant="secondary" className="text-xs">L</Badge>
                </div>
                <div className="flex justify-between">
                  <span>Reset Zoom</span>
                  <Badge variant="secondary" className="text-xs">R</Badge>
                </div>
                <div className="flex justify-between">
                  <span>Debug Info</span>
                  <Badge variant="secondary" className="text-xs">D</Badge>
                </div>
                <div className="flex justify-between">
                  <span>Search</span>
                  <Badge variant="secondary" className="text-xs">Ctrl+F</Badge>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Performance Settings */}
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <Settings className="h-4 w-4 text-primary" />
            <span>Performance</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between">
            <Label className="text-sm">Performance Mode</Label>
            <Checkbox
              checked={config.performanceMode}
              onCheckedChange={(checked) => onConfigUpdate({ performanceMode: !!checked })}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            Reduces visual quality for better performance on large graphs
          </p>
        </CardContent>
      </Card>

      {/* Graph Statistics */}
      {graphStats && (
        <Card className="glass border-border/30">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm flex items-center space-x-2">
              <Info className="h-4 w-4 text-primary" />
              <span>Graph Statistics</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <div className="flex justify-between">
              <span className="text-sm text-muted-foreground">Total Nodes</span>
              <Badge variant="outline">{graphStats.nodeCount.toLocaleString()}</Badge>
            </div>
            <div className="flex justify-between">
              <span className="text-sm text-muted-foreground">Total Edges</span>
              <Badge variant="outline">{graphStats.edgeCount.toLocaleString()}</Badge>
            </div>
            <Separator className="my-2" />
            <div className="flex justify-between">
              <span className="text-sm text-muted-foreground">Avg. Connections</span>
              <Badge variant="outline">
                {graphStats.edgeCount > 0 
                  ? (graphStats.edgeCount / graphStats.nodeCount).toFixed(1)
                  : '0'}
              </Badge>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Queue Status */}
      <Card className="glass border-border/30">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center space-x-2">
            <Activity className="h-4 w-4 text-primary" />
            <span>Queue Status</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {queueLoading ? (
            <div className="flex justify-center items-center py-2">
              <div className="animate-pulse text-sm text-muted-foreground">Loading...</div>
            </div>
          ) : queueError ? (
            <div className="text-sm text-red-400">
              Queue unavailable
            </div>
          ) : queueStatus ? (
            <>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Status</span>
                <Badge 
                  variant={
                    queueStatus.status === 'processing' ? 'default' :
                    queueStatus.status === 'idle' ? 'secondary' : 'outline'
                  }
                  className={
                    queueStatus.status === 'processing' ? 'bg-green-500/20 text-green-400 border-green-500/30' :
                    queueStatus.status === 'idle' ? 'bg-blue-500/20 text-blue-400 border-blue-500/30' :
                    'bg-gray-500/20 text-gray-400 border-gray-500/30'
                  }
                >
                  {queueStatus.status}
                </Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Pending Messages</span>
                <Badge variant="outline">{queueStatus.visible_messages.toLocaleString()}</Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Processing</span>
                <Badge variant="outline">{queueStatus.invisible_messages.toLocaleString()}</Badge>
              </div>
              <Separator className="my-2" />
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Total Processed</span>
                <Badge variant="outline">{queueStatus.total_processed.toLocaleString()}</Badge>
              </div>
              <div className="flex justify-between">
                <span className="text-sm text-muted-foreground">Success Rate</span>
                <Badge 
                  variant="outline"
                  className={
                    queueStatus.success_rate >= 95 ? 'text-green-400 border-green-500/30' :
                    queueStatus.success_rate >= 80 ? 'text-yellow-400 border-yellow-500/30' :
                    'text-red-400 border-red-500/30'
                  }
                >
                  {queueStatus.success_rate.toFixed(1)}%
                </Badge>
              </div>
            </>
          ) : (
            <div className="text-sm text-muted-foreground">
              No queue data available
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};