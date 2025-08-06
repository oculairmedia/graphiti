import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Loader2, Play, BarChart, Network, GitBranch, Activity } from 'lucide-react';
import { graphClient } from '@/api/graphClient';
import { useToast } from '@/hooks/use-toast';

interface CentralityControlsTabProps {
  onCentralityUpdate?: () => void;
}

export function CentralityControlsTab({ onCentralityUpdate }: CentralityControlsTabProps) {
  const { toast } = useToast();
  const [isCalculating, setIsCalculating] = useState(false);
  const [selectedMetric, setSelectedMetric] = useState<'all' | 'pagerank' | 'degree' | 'betweenness'>('all');
  const [storeResults, setStoreResults] = useState(false);
  
  // PageRank parameters
  const [dampingFactor, setDampingFactor] = useState(0.85);
  const [iterations, setIterations] = useState(20);
  
  // Degree centrality parameters
  const [direction, setDirection] = useState<'in' | 'out' | 'both'>('both');
  
  // Betweenness centrality parameters
  const [sampleSize, setSampleSize] = useState<number | undefined>(undefined);

  const handleCalculate = async () => {
    setIsCalculating(true);
    
    try {
      let result;
      const startTime = Date.now();
      
      switch (selectedMetric) {
        case 'pagerank':
          result = await graphClient.calculatePageRank({
            damping_factor: dampingFactor,
            iterations,
            store_results: storeResults,
          });
          break;
          
        case 'degree':
          result = await graphClient.calculateDegreeCentrality({
            direction,
            store_results: storeResults,
          });
          break;
          
        case 'betweenness':
          result = await graphClient.calculateBetweennessCentrality({
            sample_size: sampleSize,
            store_results: storeResults,
          });
          break;
          
        case 'all':
        default:
          result = await graphClient.calculateAllCentralities({
            store_results: storeResults,
          });
          break;
      }
      
      const elapsedTime = ((Date.now() - startTime) / 1000).toFixed(2);
      const nodeCount = result.nodes_processed || Object.keys(result.scores || {}).length;
      
      toast({
        title: 'Centrality Calculation Complete',
        description: `Calculated ${selectedMetric} centrality for ${nodeCount} nodes in ${elapsedTime}s`,
      });
      
      // Notify parent component to refresh data
      onCentralityUpdate?.();
      
    } catch (error) {
      console.error('Centrality calculation failed:', error);
      toast({
        title: 'Calculation Failed',
        description: error instanceof Error ? error.message : 'Failed to calculate centrality',
        variant: 'destructive',
      });
    } finally {
      setIsCalculating(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label>Centrality Metric</Label>
        <Select value={selectedMetric} onValueChange={(value: any) => setSelectedMetric(value)}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">
              <div className="flex items-center gap-2">
                <Network className="h-4 w-4" />
                All Metrics
              </div>
            </SelectItem>
            <SelectItem value="pagerank">
              <div className="flex items-center gap-2">
                <BarChart className="h-4 w-4" />
                PageRank
              </div>
            </SelectItem>
            <SelectItem value="degree">
              <div className="flex items-center gap-2">
                <GitBranch className="h-4 w-4" />
                Degree Centrality
              </div>
            </SelectItem>
            <SelectItem value="betweenness">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4" />
                Betweenness Centrality
              </div>
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* PageRank parameters */}
      {selectedMetric === 'pagerank' && (
        <>
          <div className="space-y-2">
            <Label>Damping Factor: {dampingFactor.toFixed(2)}</Label>
            <Slider
              min={0.5}
              max={0.95}
              step={0.05}
              value={[dampingFactor]}
              onValueChange={([value]) => setDampingFactor(value)}
            />
          </div>
          
          <div className="space-y-2">
            <Label>Iterations: {iterations}</Label>
            <Slider
              min={5}
              max={50}
              step={5}
              value={[iterations]}
              onValueChange={([value]) => setIterations(value)}
            />
          </div>
        </>
      )}

      {/* Degree centrality parameters */}
      {selectedMetric === 'degree' && (
        <div className="space-y-2">
          <Label>Direction</Label>
          <Select value={direction} onValueChange={(value: any) => setDirection(value)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="in">Incoming</SelectItem>
              <SelectItem value="out">Outgoing</SelectItem>
              <SelectItem value="both">Both</SelectItem>
            </SelectContent>
          </Select>
        </div>
      )}

      {/* Betweenness centrality parameters */}
      {selectedMetric === 'betweenness' && (
        <div className="space-y-2">
          <Label>Sample Size (optional)</Label>
          <input
            type="number"
            className="w-full px-3 py-2 border rounded-md"
            placeholder="Leave empty for all nodes"
            value={sampleSize || ''}
            onChange={(e) => {
              const value = e.target.value ? parseInt(e.target.value) : undefined;
              setSampleSize(value);
            }}
          />
        </div>
      )}

      <div className="flex items-center space-x-2">
        <Switch
          id="store-results"
          checked={storeResults}
          onCheckedChange={setStoreResults}
        />
        <Label htmlFor="store-results">Store results in database</Label>
      </div>

      <Button
        onClick={handleCalculate}
        disabled={isCalculating}
        className="w-full"
      >
        {isCalculating ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Calculating...
          </>
        ) : (
          <>
            <Play className="mr-2 h-4 w-4" />
            Calculate Centrality
          </>
        )}
      </Button>

      <div className="text-xs text-muted-foreground space-y-1">
        <p>• <strong>PageRank</strong>: Measures node importance based on link structure</p>
        <p>• <strong>Degree</strong>: Counts direct connections to a node</p>
        <p>• <strong>Betweenness</strong>: Measures how often a node lies on shortest paths</p>
        <p>• <strong>All Metrics</strong>: Calculates all centrality metrics at once</p>
      </div>
    </div>
  );
}