import React, { useState } from 'react';
import { Search, Filter, Route, Focus, Trash2 } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onFilterClick: () => void;
}

export const SearchBar: React.FC<SearchBarProps> = ({ 
  value, 
  onChange, 
  onFilterClick 
}) => {
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);

  // Mock autocomplete suggestions
  const mockSuggestions = [
    'Neural Network Research',
    'Machine Learning',
    'Data Science',
    'Artificial Intelligence',
    'Deep Learning',
    'Computer Vision'
  ];

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const query = e.target.value;
    onChange(query);
    
    if (query.length > 0) {
      const filtered = mockSuggestions.filter(item => 
        item.toLowerCase().includes(query.toLowerCase())
      );
      setSuggestions(filtered);
      setShowSuggestions(true);
    } else {
      setShowSuggestions(false);
    }
  };

  const selectSuggestion = (suggestion: string) => {
    onChange(suggestion);
    setShowSuggestions(false);
  };

  return (
    <div className="relative w-full">
      <div className="relative">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          type="text"
          placeholder="Search nodes, relationships, or properties..."
          value={value}
          onChange={handleInputChange}
          className="pl-10 pr-32 h-10 bg-secondary/50 border-border/30 focus:border-primary/50 transition-colors"
        />
        <div className="absolute right-2 top-1/2 transform -translate-y-1/2 flex items-center space-x-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={onFilterClick}
            className="h-6 px-2 hover:bg-primary/10"
          >
            <Filter className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 hover:bg-primary/10"
            title="Find Path"
          >
            <Route className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 hover:bg-primary/10"
            title="Focus Subgraph"
          >
            <Focus className="h-3 w-3" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 hover:bg-primary/10"
            title="Clear Selection"
          >
            <Trash2 className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* Autocomplete Dropdown */}
      {showSuggestions && suggestions.length > 0 && (
        <div className="absolute top-full mt-1 w-full glass-panel rounded-lg shadow-lg z-50 max-h-60 overflow-y-auto custom-scrollbar">
          {suggestions.map((suggestion, index) => (
            <button
              key={index}
              onClick={() => selectSuggestion(suggestion)}
              className="w-full text-left px-4 py-2 hover:bg-primary/10 transition-colors first:rounded-t-lg last:rounded-b-lg flex items-center space-x-2"
            >
              <Search className="h-3 w-3 text-muted-foreground" />
              <span className="text-sm">{suggestion}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};