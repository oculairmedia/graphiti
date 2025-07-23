import React, { useState } from 'react';
import { X, Filter, Calendar, TrendingUp, Tag } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Slider } from '@/components/ui/slider';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

interface FilterPanelProps {
  isOpen: boolean;
  onClose: () => void;
}

export const FilterPanel: React.FC<FilterPanelProps> = ({ 
  isOpen, 
  onClose 
}) => {
  const [selectedTypes, setSelectedTypes] = useState<string[]>(['Entity', 'Agent']);
  const [degreeRange, setDegreeRange] = useState([0, 100]);
  const [pagerankRange, setPagerankRange] = useState([0, 100]);
  const [dateRange, setDateRange] = useState({ start: '', end: '' });
  const [minConnections, setMinConnections] = useState('');
  const [maxConnections, setMaxConnections] = useState('');

  const nodeTypes = [
    { id: 'Entity', label: 'Entity', color: 'bg-node-entity', count: 2847 },
    { id: 'Episodic', label: 'Episodic', color: 'bg-node-episodic', count: 1024 },
    { id: 'Agent', label: 'Agent', color: 'bg-node-agent', count: 892 },
    { id: 'Community', label: 'Community', color: 'bg-node-community', count: 156 }
  ];

  const handleTypeToggle = (typeId: string) => {
    setSelectedTypes(prev => 
      prev.includes(typeId) 
        ? prev.filter(id => id !== typeId)
        : [...prev, typeId]
    );
  };

  const clearAllFilters = () => {
    setSelectedTypes(['Entity', 'Episodic', 'Agent', 'Community']);
    setDegreeRange([0, 100]);
    setPagerankRange([0, 100]);
    setDateRange({ start: '', end: '' });
    setMinConnections('');
    setMaxConnections('');
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <Card className="glass-panel w-full max-w-2xl max-h-[80vh] overflow-hidden animate-scale-in">
        <CardHeader className="pb-3 border-b border-border/20">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Filter className="h-5 w-5 text-primary" />
              <CardTitle className="text-lg">Advanced Filters</CardTitle>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="hover:bg-destructive/10"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          <Tabs defaultValue="basic" className="w-full">
            <TabsList className="grid w-full grid-cols-3 glass">
              <TabsTrigger value="basic" className="flex items-center space-x-2">
                <Tag className="h-3 w-3" />
                <span>Basic</span>
              </TabsTrigger>
              <TabsTrigger value="metrics" className="flex items-center space-x-2">
                <TrendingUp className="h-3 w-3" />
                <span>Metrics</span>
              </TabsTrigger>
              <TabsTrigger value="temporal" className="flex items-center space-x-2">
                <Calendar className="h-3 w-3" />
                <span>Time</span>
              </TabsTrigger>
            </TabsList>

            <div className="p-6 max-h-[60vh] overflow-y-auto custom-scrollbar">
              
              <TabsContent value="basic" className="mt-0 space-y-6">
                <div>
                  <h3 className="text-sm font-medium mb-4">Node Types</h3>
                  <div className="grid grid-cols-2 gap-3">
                    {nodeTypes.map((type) => (
                      <div 
                        key={type.id}
                        className="flex items-center justify-between p-3 rounded-lg border border-border/30 hover:border-primary/30 transition-colors"
                      >
                        <div className="flex items-center space-x-3">
                          <Checkbox
                            checked={selectedTypes.includes(type.id)}
                            onCheckedChange={() => handleTypeToggle(type.id)}
                          />
                          <div className={`w-3 h-3 rounded-full ${type.color}`} />
                          <span className="text-sm">{type.label}</span>
                        </div>
                        <Badge variant="outline" className="text-xs">
                          {type.count.toLocaleString()}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-medium mb-4">Properties</h3>
                  <Select>
                    <SelectTrigger className="bg-secondary/30">
                      <SelectValue placeholder="Select properties to filter by" />
                    </SelectTrigger>
                    <SelectContent className="glass">
                      <SelectItem value="author">Author</SelectItem>
                      <SelectItem value="field">Field of Study</SelectItem>
                      <SelectItem value="institution">Institution</SelectItem>
                      <SelectItem value="keywords">Keywords</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </TabsContent>

              <TabsContent value="metrics" className="mt-0 space-y-6">
                <div>
                  <div className="flex justify-between items-center mb-3">
                    <Label className="text-sm font-medium">Degree Centrality</Label>
                    <Badge variant="outline" className="text-xs">
                      {degreeRange[0]}% - {degreeRange[1]}%
                    </Badge>
                  </div>
                  <Slider
                    value={degreeRange}
                    onValueChange={setDegreeRange}
                    max={100}
                    min={0}
                    step={1}
                    className="w-full"
                  />
                </div>

                <div>
                  <div className="flex justify-between items-center mb-3">
                    <Label className="text-sm font-medium">PageRank Score</Label>
                    <Badge variant="outline" className="text-xs">
                      {pagerankRange[0]}% - {pagerankRange[1]}%
                    </Badge>
                  </div>
                  <Slider
                    value={pagerankRange}
                    onValueChange={setPagerankRange}
                    max={100}
                    min={0}
                    step={1}
                    className="w-full"
                  />
                </div>

                <div>
                  <h3 className="text-sm font-medium mb-3">Connection Count</h3>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-xs text-muted-foreground">Minimum</Label>
                      <Input
                        type="number"
                        value={minConnections}
                        onChange={(e) => setMinConnections(e.target.value)}
                        placeholder="0"
                        className="bg-secondary/30"
                      />
                    </div>
                    <div>
                      <Label className="text-xs text-muted-foreground">Maximum</Label>
                      <Input
                        type="number"
                        value={maxConnections}
                        onChange={(e) => setMaxConnections(e.target.value)}
                        placeholder="1000"
                        className="bg-secondary/30"
                      />
                    </div>
                  </div>
                </div>
              </TabsContent>

              <TabsContent value="temporal" className="mt-0 space-y-6">
                <div>
                  <h3 className="text-sm font-medium mb-3">Date Range</h3>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-xs text-muted-foreground">Start Date</Label>
                      <Input
                        type="date"
                        value={dateRange.start}
                        onChange={(e) => setDateRange(prev => ({ ...prev, start: e.target.value }))}
                        className="bg-secondary/30"
                      />
                    </div>
                    <div>
                      <Label className="text-xs text-muted-foreground">End Date</Label>
                      <Input
                        type="date"
                        value={dateRange.end}
                        onChange={(e) => setDateRange(prev => ({ ...prev, end: e.target.value }))}
                        className="bg-secondary/30"
                      />
                    </div>
                  </div>
                </div>

                <div>
                  <h3 className="text-sm font-medium mb-3">Quick Presets</h3>
                  <div className="grid grid-cols-2 gap-2">
                    <Button variant="outline" size="sm" className="h-8">
                      Last 24h
                    </Button>
                    <Button variant="outline" size="sm" className="h-8">
                      Last 7 days
                    </Button>
                    <Button variant="outline" size="sm" className="h-8">
                      Last 30 days
                    </Button>
                    <Button variant="outline" size="sm" className="h-8">
                      Last 90 days
                    </Button>
                  </div>
                </div>
              </TabsContent>

            </div>
          </Tabs>
        </CardContent>

        <div className="p-4 border-t border-border/20 flex items-center justify-between bg-secondary/20">
          <div className="flex items-center space-x-2">
            <Badge variant="secondary" className="text-xs">
              {selectedTypes.length} types selected
            </Badge>
            <Button 
              variant="ghost" 
              size="sm" 
              onClick={clearAllFilters}
              className="text-xs hover:bg-primary/10"
            >
              Clear All
            </Button>
          </div>
          <div className="flex items-center space-x-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button className="bg-primary hover:bg-primary/90">
              Apply Filters
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
};