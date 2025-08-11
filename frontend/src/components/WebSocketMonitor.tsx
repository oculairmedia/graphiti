import React, { useState, useEffect } from 'react';
import { useEnhancedWebSocketContext } from '../contexts/EnhancedWebSocketProvider';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';
import { Button } from './ui/button';
import { Progress } from './ui/progress';
import { Activity, Wifi, WifiOff, Database, Zap, Shield, Package } from 'lucide-react';

export const WebSocketMonitor: React.FC = () => {
  const {
    connectionState,
    connectionHealth,
    queueStatus,
    stats,
    forceSync,
    clearQueue,
    getDetailedStats
  } = useEnhancedWebSocketContext();

  const [detailedStats, setDetailedStats] = useState<any>(null);
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      if (showDetails) {
        setDetailedStats(getDetailedStats());
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [showDetails, getDetailedStats]);

  const getConnectionColor = () => {
    switch (connectionState) {
      case 'connected': return 'text-green-500';
      case 'connecting': return 'text-yellow-500';
      case 'reconnecting': return 'text-orange-500';
      case 'disconnected': return 'text-red-500';
      case 'failed': return 'text-red-700';
      default: return 'text-gray-500';
    }
  };

  const getQualityColor = (quality: string) => {
    switch (quality) {
      case 'excellent': return 'bg-green-500';
      case 'good': return 'bg-green-400';
      case 'fair': return 'bg-yellow-500';
      case 'poor': return 'bg-orange-500';
      case 'offline': return 'bg-red-500';
      default: return 'bg-gray-500';
    }
  };

  return (
    <div className="space-y-4">
      {/* Connection Status Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              {connectionState === 'connected' ? (
                <Wifi className="w-5 h-5 text-green-500" />
              ) : (
                <WifiOff className="w-5 h-5 text-red-500" />
              )}
              WebSocket Connection
            </span>
            <Badge className={getConnectionColor()}>
              {connectionState}
            </Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Latency</p>
              <p className="text-2xl font-bold">{connectionHealth.avgLatency}ms</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Connections</p>
              <p className="text-2xl font-bold">
                {connectionHealth.healthyConnections}/{connectionHealth.totalConnections}
              </p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Quality</p>
              <div className="flex items-center gap-1 mt-2">
                {['excellent', 'good', 'fair', 'poor'].map((quality, i) => (
                  <div
                    key={quality}
                    className={`h-6 w-2 rounded ${
                      i <= ['excellent', 'good', 'fair', 'poor'].indexOf(
                        connectionHealth.avgLatency < 50 ? 'excellent' :
                        connectionHealth.avgLatency < 150 ? 'good' :
                        connectionHealth.avgLatency < 300 ? 'fair' : 'poor'
                      ) ? getQualityColor(quality) : 'bg-gray-300'
                    }`}
                  />
                ))}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Performance Stats Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="w-5 h-5" />
            Performance Metrics
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm">Messages Received</span>
              <Badge variant="secondary">{stats.messagesReceived}</Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm">Duplicates Detected</span>
              <Badge variant={stats.duplicatesDetected > 0 ? 'destructive' : 'secondary'}>
                {stats.duplicatesDetected}
              </Badge>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-sm">Conflicts Resolved</span>
              <Badge variant="outline">{stats.conflictsResolved}</Badge>
            </div>
            <div>
              <div className="flex justify-between items-center mb-1">
                <span className="text-sm">Compression Ratio</span>
                <span className="text-sm font-medium">
                  {(stats.compressionRatio * 100).toFixed(1)}%
                </span>
              </div>
              <Progress value={stats.compressionRatio * 100} className="h-2" />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Offline Queue Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Database className="w-5 h-5" />
              Offline Queue
            </span>
            {queueStatus.isSyncing && (
              <Badge className="animate-pulse">Syncing...</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-sm">Queue Size</span>
              <Badge variant={queueStatus.queueSize > 0 ? 'warning' : 'secondary'}>
                {queueStatus.queueSize} messages
              </Badge>
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                onClick={forceSync}
                disabled={queueStatus.queueSize === 0 || queueStatus.isSyncing}
              >
                <Zap className="w-4 h-4 mr-1" />
                Force Sync
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={clearQueue}
                disabled={queueStatus.queueSize === 0}
              >
                Clear Queue
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Advanced Features Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="w-5 h-5" />
            Enhanced Features
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-500 rounded-full" />
              <span className="text-sm">Connection Pooling</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-500 rounded-full" />
              <span className="text-sm">Health Monitoring</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-500 rounded-full" />
              <span className="text-sm">Conflict Resolution</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-500 rounded-full" />
              <span className="text-sm">Delta Compression</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-500 rounded-full" />
              <span className="text-sm">Message Deduplication</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-green-500 rounded-full" />
              <span className="text-sm">Offline Queue</span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Detailed Stats (collapsible) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Package className="w-5 h-5" />
              Detailed Statistics
            </span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setShowDetails(!showDetails)}
            >
              {showDetails ? 'Hide' : 'Show'} Details
            </Button>
          </CardTitle>
        </CardHeader>
        {showDetails && detailedStats && (
          <CardContent>
            <pre className="text-xs bg-muted p-3 rounded overflow-auto max-h-96">
              {JSON.stringify(detailedStats, null, 2)}
            </pre>
          </CardContent>
        )}
      </Card>
    </div>
  );
};