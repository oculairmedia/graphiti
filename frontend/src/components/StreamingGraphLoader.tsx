/**
 * Component demonstrating streaming graph data loading
 * Shows progress and allows cancellation
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useStreamingData } from '../hooks/useStreamingData';
import { Button } from './ui/button';
import { Progress } from './ui/progress';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Alert, AlertDescription } from './ui/alert';
import { Play, Pause, RotateCcw, AlertCircle, CheckCircle2 } from 'lucide-react';
import { duckdbService } from '../services/duckdb-service';
import { logger } from '../utils/logger';

interface StreamingGraphLoaderProps {
  onDataLoaded?: (nodes: any[], links: any[]) => void;
  className?: string;
}

export const StreamingGraphLoader: React.FC<StreamingGraphLoaderProps> = ({
  onDataLoaded,
  className = ''
}) => {
  const {
    nodes,
    links,
    isStreaming,
    progress,
    chunksProcessed,
    totalChunks,
    error,
    startStreaming,
    streamFromDuckDB,
    abortStream,
    clearData,
    getStats
  } = useStreamingData({
    chunkSize: 1024 * 512, // 512KB chunks
    maxNodes: 50000,
    maxLinks: 100000,
    useWorker: true,
    onChunkReceived: (newNodes, newLinks) => {
      // Update visualization incrementally
      logger.log('[StreamingLoader] Chunk received:', {
        newNodes: newNodes.length,
        newLinks: newLinks.length
      });
    },
    onStreamComplete: () => {
      logger.log('[StreamingLoader] Streaming complete');
      if (onDataLoaded) {
        onDataLoaded(nodes, links);
      }
    }
  });

  const [streamMode, setStreamMode] = useState<'url' | 'duckdb'>('duckdb');
  const [streamUrl, setStreamUrl] = useState('http://localhost:3000/api/arrow/nodes');
  const [isDuckDBReady, setIsDuckDBReady] = useState(false);
  const [stats, setStats] = useState<any>(null);

  // Check DuckDB readiness
  useEffect(() => {
    const checkDuckDB = async () => {
      const isReady = duckdbService.isInitialized();
      setIsDuckDBReady(isReady);
      
      if (!isReady) {
        // Try to initialize
        try {
          await duckdbService.initialize();
          setIsDuckDBReady(true);
        } catch (error) {
          logger.error('[StreamingLoader] Failed to initialize DuckDB:', error);
        }
      }
    };
    
    checkDuckDB();
  }, []);

  // Update stats periodically
  useEffect(() => {
    if (isStreaming) {
      const interval = setInterval(() => {
        setStats(getStats());
      }, 500);
      
      return () => clearInterval(interval);
    }
  }, [isStreaming, getStats]);

  const handleStartStreaming = useCallback(async () => {
    if (streamMode === 'url') {
      await startStreaming(streamUrl);
    } else if (streamMode === 'duckdb' && isDuckDBReady) {
      const connection = duckdbService.getDuckDBConnection();
      if (connection) {
        await streamFromDuckDB(
          connection.connection,
          'SELECT * FROM nodes ORDER BY idx LIMIT 10000'
        );
      }
    }
  }, [streamMode, streamUrl, isDuckDBReady, startStreaming, streamFromDuckDB]);

  const handleReset = useCallback(() => {
    clearData();
    setStats(null);
  }, [clearData]);

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  };

  const progressPercentage = totalChunks > 0 
    ? (chunksProcessed / totalChunks) * 100
    : isStreaming ? 50 : 0;

  return (
    <Card className={`w-full max-w-2xl ${className}`}>
      <CardHeader>
        <CardTitle>Streaming Data Pipeline</CardTitle>
        <CardDescription>
          Progressive loading with real-time updates
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Stream Mode Selection */}
        <div className="flex gap-2">
          <Button
            variant={streamMode === 'duckdb' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStreamMode('duckdb')}
            disabled={isStreaming}
          >
            DuckDB Stream
          </Button>
          <Button
            variant={streamMode === 'url' ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStreamMode('url')}
            disabled={isStreaming}
          >
            URL Stream
          </Button>
        </div>

        {/* URL Input (if URL mode) */}
        {streamMode === 'url' && (
          <input
            type="text"
            value={streamUrl}
            onChange={(e) => setStreamUrl(e.target.value)}
            disabled={isStreaming}
            placeholder="Enter Arrow data URL"
            className="w-full px-3 py-2 border rounded-md"
          />
        )}

        {/* DuckDB Status */}
        {streamMode === 'duckdb' && (
          <Alert className={isDuckDBReady ? 'border-green-500' : 'border-yellow-500'}>
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              DuckDB: {isDuckDBReady ? 'Ready' : 'Initializing...'}
            </AlertDescription>
          </Alert>
        )}

        {/* Progress Bar */}
        {(isStreaming || progressPercentage > 0) && (
          <div className="space-y-2">
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>Progress</span>
              <span>{progressPercentage.toFixed(0)}%</span>
            </div>
            <Progress value={progressPercentage} className="h-2" />
            {chunksProcessed > 0 && (
              <div className="text-xs text-muted-foreground">
                Chunks: {chunksProcessed} / {totalChunks || '?'}
              </div>
            )}
          </div>
        )}

        {/* Statistics */}
        {stats && (
          <div className="grid grid-cols-2 gap-4 p-4 bg-secondary/20 rounded-lg">
            <div>
              <div className="text-sm font-medium">Nodes</div>
              <div className="text-2xl font-bold">{stats.totalNodes.toLocaleString()}</div>
              <div className="text-xs text-muted-foreground">
                ~{formatBytes(stats.memoryUsage.nodes)}
              </div>
            </div>
            <div>
              <div className="text-sm font-medium">Links</div>
              <div className="text-2xl font-bold">{stats.totalLinks.toLocaleString()}</div>
              <div className="text-xs text-muted-foreground">
                ~{formatBytes(stats.memoryUsage.links)}
              </div>
            </div>
          </div>
        )}

        {/* Error Display */}
        {error && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              {error.message}
            </AlertDescription>
          </Alert>
        )}

        {/* Success Message */}
        {!isStreaming && nodes.length > 0 && (
          <Alert className="border-green-500">
            <CheckCircle2 className="h-4 w-4" />
            <AlertDescription>
              Successfully loaded {nodes.length} nodes and {links.length} links
            </AlertDescription>
          </Alert>
        )}

        {/* Control Buttons */}
        <div className="flex gap-2">
          {!isStreaming ? (
            <>
              <Button
                onClick={handleStartStreaming}
                disabled={streamMode === 'duckdb' && !isDuckDBReady}
                className="flex-1"
              >
                <Play className="h-4 w-4 mr-2" />
                Start Streaming
              </Button>
              {nodes.length > 0 && (
                <Button
                  onClick={handleReset}
                  variant="outline"
                >
                  <RotateCcw className="h-4 w-4 mr-2" />
                  Reset
                </Button>
              )}
            </>
          ) : (
            <Button
              onClick={abortStream}
              variant="destructive"
              className="flex-1"
            >
              <Pause className="h-4 w-4 mr-2" />
              Stop Streaming
            </Button>
          )}
        </div>

        {/* Info Text */}
        <div className="text-xs text-muted-foreground text-center">
          {isStreaming 
            ? 'Streaming data in progress...'
            : 'Click "Start Streaming" to begin progressive loading'
          }
        </div>
      </CardContent>
    </Card>
  );
};

export default StreamingGraphLoader;