import React, { useState, useEffect } from 'react';
import { useGraphCache } from '../hooks/useGraphCache';
import { useWebSocketContext } from '../contexts/WebSocketProvider';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Button } from './ui/button';
import { Progress } from './ui/progress';
import { Badge } from './ui/badge';
import { Trash2, RefreshCw, Wifi, WifiOff, Activity, Database } from 'lucide-react';
import { cn } from '../lib/utils';

export function CacheControl() {
  const { 
    isInitialized, 
    cacheStats, 
    updateStats,
    clearCache, 
    invalidate,
    prefetch 
  } = useGraphCache();
  
  const { 
    isConnected, 
    connectionQuality, 
    latency 
  } = useWebSocketContext();
  
  const [isInvalidating, setIsInvalidating] = useState(false);
  const [isPrefetching, setIsPrefetching] = useState(false);

  const handleClearCache = () => {
    setIsInvalidating(true);
    clearCache();
    setTimeout(() => setIsInvalidating(false), 500);
  };

  const handlePrefetch = async () => {
    setIsPrefetching(true);
    await prefetch(['graph:full', 'nodes:entity', 'nodes:relationship']);
    setIsPrefetching(false);
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  };

  const getConnectionColor = () => {
    if (!isConnected) return 'text-destructive';
    switch (connectionQuality) {
      case 'excellent': return 'text-green-500';
      case 'good': return 'text-yellow-500';
      case 'poor': return 'text-orange-500';
      default: return 'text-muted-foreground';
    }
  };

  const getConnectionIcon = () => {
    return isConnected ? (
      <Wifi className={cn("h-4 w-4", getConnectionColor())} />
    ) : (
      <WifiOff className="h-4 w-4 text-destructive" />
    );
  };

  return (
    <Card className="w-full">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg font-medium">Cache & Connection</CardTitle>
          <div className="flex items-center gap-2">
            {getConnectionIcon()}
            <Badge variant={isConnected ? "default" : "destructive"}>
              {isConnected ? `${connectionQuality} (${latency}ms)` : 'Disconnected'}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Cache Stats */}
        {isInitialized && cacheStats && (
          <>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-muted-foreground">Cache Entries</p>
                <p className="text-2xl font-semibold">
                  {cacheStats.validEntries}/{cacheStats.totalEntries}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Hit Rate</p>
                <p className="text-2xl font-semibold">
                  {cacheStats.hitRate.toFixed(1)}%
                </p>
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted-foreground">Memory Usage</span>
                <span>{formatBytes(cacheStats.totalSizeBytes)}</span>
              </div>
              <Progress 
                value={(cacheStats.totalSizeBytes / (10 * 1024 * 1024)) * 100} 
                className="h-2"
              />
            </div>

            {cacheStats.expiredEntries > 0 && (
              <div className="flex items-center gap-2 text-sm text-yellow-600">
                <Activity className="h-4 w-4" />
                <span>{cacheStats.expiredEntries} expired entries pending cleanup</span>
              </div>
            )}
          </>
        )}

        {/* WebSocket Stats */}
        {updateStats && (
          <div className="border-t pt-4">
            <div className="grid grid-cols-3 gap-2 text-sm">
              <div className="text-center">
                <p className="text-muted-foreground text-xs">Total Updates</p>
                <p className="font-semibold">{updateStats.totalUpdates}</p>
              </div>
              <div className="text-center">
                <p className="text-muted-foreground text-xs">Delta Updates</p>
                <p className="font-semibold">{updateStats.deltaUpdates}</p>
              </div>
              <div className="text-center">
                <p className="text-muted-foreground text-xs">Invalidations</p>
                <p className="font-semibold">{updateStats.cacheInvalidations}</p>
              </div>
            </div>
            
            {updateStats.lastUpdateTime && (
              <p className="text-xs text-muted-foreground text-center mt-2">
                Last update: {new Date(updateStats.lastUpdateTime).toLocaleTimeString()}
              </p>
            )}
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex gap-2 pt-2">
          <Button
            variant="outline"
            size="sm"
            onClick={handleClearCache}
            disabled={isInvalidating || !isInitialized}
            className="flex-1"
          >
            <Trash2 className="h-4 w-4 mr-1" />
            Clear Cache
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handlePrefetch}
            disabled={isPrefetching || !isInitialized || !isConnected}
            className="flex-1"
          >
            <Database className="h-4 w-4 mr-1" />
            {isPrefetching ? 'Prefetching...' : 'Prefetch'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}