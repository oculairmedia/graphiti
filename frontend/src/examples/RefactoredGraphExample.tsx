import React, { useState, useRef, useCallback, useEffect } from 'react';
import { 
  GraphContainer,
  GraphViewport,
  useGraphData,
  useWebSocketManager,
  type GraphViewportHandle,
  type GraphNode,
  type GraphLink
} from '../components/graph';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { 
  Download, 
  Upload, 
  ZoomIn, 
  ZoomOut, 
  Maximize2,
  RefreshCw,
  Play,
  Pause,
  Settings
} from 'lucide-react';

/**
 * Example implementation showing how to use the refactored graph components
 * This demonstrates various usage patterns and features
 */
export const RefactoredGraphExample: React.FC = () => {
  // State
  const [selectedNodes, setSelectedNodes] = useState<GraphNode[]>([]);
  const [isSimulationRunning, setIsSimulationRunning] = useState(true);
  const [theme, setTheme] = useState<'dark' | 'light'>('dark');
  const [showStats, setShowStats] = useState(true);
  
  // Refs
  const viewportRef = useRef<GraphViewportHandle>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Example 1: Basic usage with static data
  const BasicExample = () => (
    <GraphContainer
      initialNodes={[
        { id: '1', name: 'Node 1', node_type: 'Entity', properties: {} },
        { id: '2', name: 'Node 2', node_type: 'Entity', properties: {} },
        { id: '3', name: 'Node 3', node_type: 'Episodic', properties: {} },
      ]}
      initialLinks={[
        { source: '1', target: '2' },
        { source: '2', target: '3' },
      ]}
      width={800}
      height={400}
      theme={theme}
    />
  );

  // Example 2: With data fetching from API
  const ApiExample = () => (
    <GraphContainer
      dataUrl="/api/visualize?query_type=entire_graph"
      width={800}
      height={400}
      theme={theme}
      onError={(error) => {
        console.error('Failed to load graph:', error);
      }}
    />
  );

  // Example 3: With real-time updates
  const RealTimeExample = () => (
    <GraphContainer
      dataUrl="/api/visualize?query_type=entire_graph"
      webSocketUrl="ws://192.168.50.90:4543/ws"
      enableRealTimeUpdates={true}
      enableDeltaProcessing={true}
      width={800}
      height={400}
      theme={theme}
      onNodeClick={(node) => {
        console.log('Node clicked:', node);
        setSelectedNodes([node]);
      }}
      onSelectionChange={(nodes) => {
        setSelectedNodes(nodes);
      }}
    />
  );

  // Example 4: Advanced usage with custom hooks
  const AdvancedExample = () => {
    const [graphData, graphActions] = useGraphData({
      enableDeltaProcessing: true,
      maxHistorySize: 20
    });

    const [wsState, wsActions] = useWebSocketManager(
      {
        url: 'ws://192.168.50.90:4543/ws',
        reconnectAttempts: 5,
        batchUpdates: true,
      },
      (message) => {
        console.log('WebSocket message:', message);
      },
      (delta) => {
        graphActions.applyDelta(delta);
      }
    );

    // Load data on mount
    useEffect(() => {
      fetch('/api/visualize?query_type=entire_graph')
        .then(res => res.json())
        .then(data => {
          graphActions.setNodes(data.data?.nodes || []);
          graphActions.setLinks(data.data?.edges || []);
        })
        .catch(error => {
          graphActions.setError(error.message);
        });
    }, []);

    return (
      <div className="relative w-full h-full">
        <GraphViewport
          ref={viewportRef}
          nodes={graphData.nodes}
          links={graphData.links}
          width={800}
          height={400}
          backgroundColor={theme === 'dark' ? '#0a0a0a' : '#f5f5f5'}
          nodeColor={(node) => {
            if (node.node_type === 'Entity') return '#4FC3F7';
            if (node.node_type === 'Episodic') return '#66BB6A';
            return '#4A90E2';
          }}
          onNodeClick={(node) => {
            console.log('Node clicked:', node);
            setSelectedNodes([node]);
          }}
          showLabels={true}
          enablePanning={true}
          enableZooming={true}
        />
        
        {/* Stats overlay */}
        {showStats && (
          <div className="absolute top-2 left-2 space-y-2">
            <Badge variant="secondary">
              Nodes: {graphData.stats.totalNodes}
            </Badge>
            <Badge variant="secondary">
              Edges: {graphData.stats.totalEdges}
            </Badge>
            {wsState.isConnected && (
              <Badge variant="default" className="bg-green-500">
                Live
              </Badge>
            )}
          </div>
        )}
      </div>
    );
  };

  // Control panel
  const ControlPanel = () => (
    <div className="flex gap-2 p-4 bg-background border-t">
      <Button
        size="sm"
        variant="outline"
        onClick={() => viewportRef.current?.zoomTo(2)}
      >
        <ZoomIn className="h-4 w-4" />
      </Button>
      
      <Button
        size="sm"
        variant="outline"
        onClick={() => viewportRef.current?.zoomTo(0.5)}
      >
        <ZoomOut className="h-4 w-4" />
      </Button>
      
      <Button
        size="sm"
        variant="outline"
        onClick={() => viewportRef.current?.fitToNodes()}
      >
        <Maximize2 className="h-4 w-4" />
      </Button>
      
      <Button
        size="sm"
        variant="outline"
        onClick={() => viewportRef.current?.resetViewport()}
      >
        <RefreshCw className="h-4 w-4" />
      </Button>
      
      <div className="flex-1" />
      
      <Button
        size="sm"
        variant="outline"
        onClick={() => setIsSimulationRunning(!isSimulationRunning)}
      >
        {isSimulationRunning ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
      </Button>
      
      <Button
        size="sm"
        variant="outline"
        onClick={async () => {
          const blob = await viewportRef.current?.exportImage('png');
          if (blob) {
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `graph-${Date.now()}.png`;
            a.click();
            URL.revokeObjectURL(url);
          }
        }}
      >
        <Download className="h-4 w-4" />
      </Button>
      
      <Button
        size="sm"
        variant="outline"
        onClick={() => fileInputRef.current?.click()}
      >
        <Upload className="h-4 w-4" />
      </Button>
      
      <input
        ref={fileInputRef}
        type="file"
        accept=".json"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) {
            const reader = new FileReader();
            reader.onload = (event) => {
              try {
                const data = JSON.parse(event.target?.result as string);
                // Handle uploaded data
                console.log('Uploaded data:', data);
              } catch (error) {
                console.error('Failed to parse file:', error);
              }
            };
            reader.readAsText(file);
          }
        }}
      />
      
      <Button
        size="sm"
        variant="outline"
        onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
      >
        <Settings className="h-4 w-4" />
      </Button>
    </div>
  );

  // Node details panel
  const NodeDetailsPanel = () => (
    <Card className="w-80">
      <CardHeader>
        <CardTitle>Selected Nodes</CardTitle>
      </CardHeader>
      <CardContent>
        {selectedNodes.length === 0 ? (
          <p className="text-muted-foreground">No nodes selected</p>
        ) : (
          <div className="space-y-2">
            {selectedNodes.map(node => (
              <div key={node.id} className="p-2 border rounded">
                <div className="font-semibold">{node.name || node.id}</div>
                <div className="text-sm text-muted-foreground">
                  Type: {node.node_type}
                </div>
                {node.properties && (
                  <div className="text-xs mt-1">
                    {Object.entries(node.properties).slice(0, 3).map(([key, value]) => (
                      <div key={key}>
                        {key}: {String(value)}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );

  return (
    <div className="h-screen flex flex-col">
      <div className="p-4 border-b">
        <h1 className="text-2xl font-bold">Refactored Graph Components Examples</h1>
        <p className="text-muted-foreground">
          Demonstrating the new modular architecture
        </p>
      </div>
      
      <div className="flex-1 flex">
        <div className="flex-1">
          <Tabs defaultValue="realtime" className="h-full flex flex-col">
            <TabsList className="mx-4 mt-4">
              <TabsTrigger value="basic">Basic</TabsTrigger>
              <TabsTrigger value="api">API Data</TabsTrigger>
              <TabsTrigger value="realtime">Real-time</TabsTrigger>
              <TabsTrigger value="advanced">Advanced</TabsTrigger>
            </TabsList>
            
            <TabsContent value="basic" className="flex-1 p-4">
              <Card className="h-full">
                <CardHeader>
                  <CardTitle>Basic Static Graph</CardTitle>
                </CardHeader>
                <CardContent>
                  <BasicExample />
                </CardContent>
              </Card>
            </TabsContent>
            
            <TabsContent value="api" className="flex-1 p-4">
              <Card className="h-full">
                <CardHeader>
                  <CardTitle>API Data Loading</CardTitle>
                </CardHeader>
                <CardContent>
                  <ApiExample />
                </CardContent>
              </Card>
            </TabsContent>
            
            <TabsContent value="realtime" className="flex-1 p-4">
              <Card className="h-full">
                <CardHeader>
                  <CardTitle>Real-time Updates</CardTitle>
                </CardHeader>
                <CardContent>
                  <RealTimeExample />
                </CardContent>
              </Card>
            </TabsContent>
            
            <TabsContent value="advanced" className="flex-1 p-4">
              <Card className="h-full">
                <CardHeader>
                  <CardTitle>Advanced with Custom Hooks</CardTitle>
                </CardHeader>
                <CardContent>
                  <AdvancedExample />
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
          
          <ControlPanel />
        </div>
        
        <div className="w-80 p-4 border-l">
          <NodeDetailsPanel />
          
          <div className="mt-4 space-y-2">
            <Button
              variant="outline"
              className="w-full"
              onClick={() => setShowStats(!showStats)}
            >
              {showStats ? 'Hide' : 'Show'} Stats
            </Button>
            
            <div className="text-sm text-muted-foreground">
              <p>Keyboard Shortcuts:</p>
              <ul className="mt-1 space-y-1">
                <li>• Ctrl+A: Select all</li>
                <li>• Escape: Clear selection</li>
                <li>• F: Fit view</li>
                <li>• R: Reset viewport</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};