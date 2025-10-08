# Low Priority Issue #026: Missing Data Export Features

## Severity
🟢 **Low**

## Component
Application-wide - No data export functionality for graph data, views, or analysis results

## Issue Description
The application lacks data export capabilities, preventing users from saving graph data, exporting visualizations, or sharing analysis results. This limits the application's utility for research, reporting, and collaboration workflows where users need to extract insights and data from the graph visualization.

## Technical Details

### Missing Export Features

#### 1. Graph Data Export
```typescript
// Currently missing functionality to export:
// - Node data as CSV/JSON/XML
// - Edge data as CSV/JSON/XML
// - Complete graph structure
// - Filtered/selected subsets
// - Graph statistics and metrics
// - Search results
```

#### 2. Visualization Export
```typescript
// No image/PDF export capabilities:
// - Screenshot of current graph view
// - High-resolution PNG/SVG export
// - PDF reports with graph and data
// - Vector graphics for publications
// - Print-friendly formats
```

#### 3. Analysis Results Export
```typescript
// No export for analytical data:
// - Centrality calculations
// - Community detection results
// - Path analysis results
// - Node/edge metrics
// - Filter configurations
// - Search results with context
```

#### 4. Configuration Export
```typescript
// No way to save/share:
// - Current view settings
// - Filter configurations
// - Color schemes and styling
// - Layout parameters
// - User preferences
```

### Current Implementation Gaps

#### 1. No Export UI Components
```typescript
// Missing export functionality in UI
export const ControlPanel: React.FC<ControlPanelProps> = ({ onFilterClick, onStatsClick }) => {
  // ❌ No export button or menu
  // ❌ No download functionality
  // ❌ No format selection options
  
  return (
    <div className="absolute top-4 right-4 flex flex-col space-y-2">
      <Button variant="outline" size="sm" onClick={onFilterClick}>
        <Filter className="h-4 w-4" />
      </Button>
      <Button variant="outline" size="sm" onClick={onStatsClick}>
        <BarChart3 className="h-4 w-4" />
      </Button>
      {/* ❌ Missing export button */}
    </div>
  );
};
```

#### 2. No Data Serialization
```typescript
// GraphViz.tsx - No methods to serialize graph data
const GraphViz: React.FC<GraphVizProps> = ({ data, isLoading, className }) => {
  // ❌ No functions to export data
  // ❌ No data transformation for export formats
  // ❌ No filtering for export subsets
  
  const exportGraphData = () => {
    // ❌ Function doesn't exist
  };
  
  const exportVisualization = () => {
    // ❌ Function doesn't exist
  };
};
```

#### 3. No File Generation Utilities
```typescript
// Missing utilities for:
// - CSV file generation
// - JSON file downloads
// - Image capture and download
// - PDF generation
// - ZIP archive creation for multiple exports
```

#### 4. No Export Configuration
```typescript
// Missing export options:
// - File format selection
// - Data filtering options
// - Image resolution settings
// - Compression options
// - Metadata inclusion
```

## Root Cause Analysis

### 1. Core Functionality Focus
Development prioritized visualization and interaction over data export features.

### 2. Complex Data Structures
Graph data export requires thoughtful consideration of format and structure.

### 3. Browser Limitations
Client-side file generation has browser compatibility and performance considerations.

### 4. Export Requirements Unclear
No clear requirements for what export formats and features are needed.

## Impact Assessment

### User Workflow Limitations
- **Research Use**: Cannot extract data for further analysis in other tools
- **Reporting**: Cannot create reports with graph visualizations
- **Sharing**: Cannot share specific views or findings with others
- **Backup**: Cannot save current work or configurations

### Professional Use Cases
- **Academic Research**: Need to export data for papers and publications
- **Business Analysis**: Need to create presentations with graph insights
- **Data Integration**: Need to export results to other analytical tools
- **Compliance**: May need to export data for audit or regulatory purposes

### Competitive Disadvantage
- **Feature Completeness**: Other graph tools typically include export features
- **Workflow Integration**: Doesn't fit into existing data analysis pipelines
- **Professional Adoption**: Less suitable for professional/enterprise use

## Scenarios Where Export Features Are Needed

### Scenario 1: Research Publication
```typescript
// Researcher analyzing social network data
// Needs to:
// 1. Export high-resolution graph visualization for paper
// 2. Export centrality metrics as CSV for statistical analysis
// 3. Export subgraph data for specific communities
// 4. Create reproducible research by exporting configuration

// Current workaround: Screenshot and manual data extraction
// Desired: One-click export with multiple format options
```

### Scenario 2: Business Presentation
```typescript
// Analyst preparing executive presentation
// Needs to:
// 1. Export graph visualization as PowerPoint-compatible image
// 2. Export key metrics and statistics as tables
// 3. Create PDF report with multiple graph views
// 4. Export filtered data showing specific business entities

// Current workaround: Screenshots and manual data compilation
// Desired: Integrated export to presentation formats
```

### Scenario 3: Data Pipeline Integration
```typescript
// Data scientist working with multiple tools
// Needs to:
// 1. Export graph data to feed into ML models
// 2. Export community detection results for further analysis
// 3. Export node/edge lists for use in other graph tools
// 4. Export filtered results based on analysis criteria

// Current workaround: Reconstruct data from original sources
// Desired: Direct export to standard data formats
```

## Proposed Solutions

### Solution 1: Comprehensive Export System
```typescript
// src/utils/exportUtils.ts
export class GraphExporter {
  constructor(private graphData: GraphData) {}
  
  // Data export methods
  exportNodesAsCSV(selectedOnly: boolean = false): string {
    const nodes = selectedOnly ? this.getSelectedNodes() : this.graphData.nodes;
    const headers = ['id', 'label', 'type', 'properties'];
    const csvRows = [headers.join(',')];
    
    nodes.forEach(node => {
      const row = [
        this.escapeCSV(node.id),
        this.escapeCSV(node.label || ''),
        this.escapeCSV(node.node_type),
        this.escapeCSV(JSON.stringify(node.properties || {}))
      ];
      csvRows.push(row.join(','));
    });
    
    return csvRows.join('\n');
  }
  
  exportEdgesAsCSV(selectedOnly: boolean = false): string {
    const edges = selectedOnly ? this.getSelectedEdges() : this.graphData.edges;
    const headers = ['from', 'to', 'id', 'properties'];
    const csvRows = [headers.join(',')];
    
    edges.forEach(edge => {
      const row = [
        this.escapeCSV(edge.from),
        this.escapeCSV(edge.to),
        this.escapeCSV(edge.id || ''),
        this.escapeCSV(JSON.stringify(edge.properties || {}))
      ];
      csvRows.push(row.join(','));
    });
    
    return csvRows.join('\n');
  }
  
  exportGraphAsJSON(options: ExportOptions = {}): string {
    const exportData = {
      metadata: {
        exportedAt: new Date().toISOString(),
        version: '1.0',
        totalNodes: this.graphData.nodes.length,
        totalEdges: this.graphData.edges.length,
        ...options.metadata
      },
      nodes: options.selectedOnly ? this.getSelectedNodes() : this.graphData.nodes,
      edges: options.selectedOnly ? this.getSelectedEdges() : this.graphData.edges,
      statistics: options.includeStats ? this.calculateStatistics() : undefined
    };
    
    return JSON.stringify(exportData, null, 2);
  }
  
  exportGraphML(): string {
    // GraphML format for compatibility with other graph tools
    const xml = ['<?xml version="1.0" encoding="UTF-8"?>'];
    xml.push('<graphml xmlns="http://graphml.graphdrawing.org/xmlns">');
    xml.push('  <graph id="G" edgedefault="directed">');
    
    // Export nodes
    this.graphData.nodes.forEach(node => {
      xml.push(`    <node id="${this.escapeXML(node.id)}">`);
      xml.push(`      <data key="label">${this.escapeXML(node.label || '')}</data>`);
      xml.push(`      <data key="type">${this.escapeXML(node.node_type)}</data>`);
      xml.push('    </node>');
    });
    
    // Export edges
    this.graphData.edges.forEach(edge => {
      xml.push(`    <edge source="${this.escapeXML(edge.from)}" target="${this.escapeXML(edge.to)}">`);
      xml.push('    </edge>');
    });
    
    xml.push('  </graph>');
    xml.push('</graphml>');
    
    return xml.join('\n');
  }
  
  // Utility methods
  private escapeCSV(str: string): string {
    if (str.includes(',') || str.includes('"') || str.includes('\n')) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  }
  
  private escapeXML(str: string): string {
    return str
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&apos;');
  }
  
  private getSelectedNodes() {
    // Implementation to get currently selected nodes
    return this.graphData.nodes; // Placeholder
  }
  
  private getSelectedEdges() {
    // Implementation to get edges for selected nodes
    return this.graphData.edges; // Placeholder
  }
  
  private calculateStatistics() {
    return {
      nodeCount: this.graphData.nodes.length,
      edgeCount: this.graphData.edges.length,
      density: this.graphData.edges.length / (this.graphData.nodes.length * (this.graphData.nodes.length - 1))
    };
  }
}

interface ExportOptions {
  selectedOnly?: boolean;
  includeStats?: boolean;
  metadata?: Record<string, any>;
}
```

### Solution 2: Image Export Functionality
```typescript
// src/utils/imageExport.ts
export class ImageExporter {
  constructor(private canvasRef: React.RefObject<HTMLCanvasElement>) {}
  
  async exportAsPNG(options: ImageExportOptions = {}): Promise<void> {
    const canvas = this.canvasRef.current;
    if (!canvas) throw new Error('Canvas not available');
    
    const {
      width = canvas.width,
      height = canvas.height,
      quality = 1.0,
      backgroundColor = '#ffffff'
    } = options;
    
    // Create high-resolution canvas
    const exportCanvas = document.createElement('canvas');
    exportCanvas.width = width;
    exportCanvas.height = height;
    const ctx = exportCanvas.getContext('2d')!;
    
    // Fill background
    ctx.fillStyle = backgroundColor;
    ctx.fillRect(0, 0, width, height);
    
    // Draw current canvas content
    ctx.drawImage(canvas, 0, 0, width, height);
    
    // Convert to blob and download
    exportCanvas.toBlob((blob) => {
      if (blob) {
        this.downloadBlob(blob, 'graph-export.png');
      }
    }, 'image/png', quality);
  }
  
  async exportAsSVG(options: SVGExportOptions = {}): Promise<void> {
    const {
      width = 1200,
      height = 800,
      includeStyles = true
    } = options;
    
    // Create SVG representation of the graph
    const svg = this.createSVGFromGraph(width, height, includeStyles);
    const blob = new Blob([svg], { type: 'image/svg+xml' });
    this.downloadBlob(blob, 'graph-export.svg');
  }
  
  async exportAsPDF(options: PDFExportOptions = {}): Promise<void> {
    // Use jsPDF or similar library
    const { jsPDF } = await import('jspdf');
    const pdf = new jsPDF();
    
    // Get canvas as image
    const canvas = this.canvasRef.current;
    if (!canvas) throw new Error('Canvas not available');
    
    const imgData = canvas.toDataURL('image/png');
    const imgWidth = 210; // A4 width in mm
    const pageHeight = 295; // A4 height in mm
    const imgHeight = (canvas.height * imgWidth) / canvas.width;
    
    pdf.addImage(imgData, 'PNG', 0, 0, imgWidth, imgHeight);
    
    // Add metadata and statistics if requested
    if (options.includeMetadata) {
      this.addMetadataToPDF(pdf, options.metadata);
    }
    
    pdf.save('graph-export.pdf');
  }
  
  private createSVGFromGraph(width: number, height: number, includeStyles: boolean): string {
    // Create SVG representation
    // This would need to recreate the graph structure in SVG format
    // For now, placeholder implementation
    return `
      <svg width="${width}" height="${height}" xmlns="http://www.w3.org/2000/svg">
        <rect width="100%" height="100%" fill="white"/>
        <text x="50%" y="50%" text-anchor="middle">Graph SVG Export</text>
      </svg>
    `;
  }
  
  private downloadBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }
  
  private addMetadataToPDF(pdf: any, metadata?: Record<string, any>): void {
    // Add a second page with metadata
    pdf.addPage();
    pdf.setFontSize(16);
    pdf.text('Graph Export Metadata', 20, 30);
    
    pdf.setFontSize(12);
    let y = 50;
    const defaultMetadata = {
      'Export Date': new Date().toISOString(),
      'Export Type': 'Graph Visualization',
      'Format': 'PDF'
    };
    
    const allMetadata = { ...defaultMetadata, ...metadata };
    
    Object.entries(allMetadata).forEach(([key, value]) => {
      pdf.text(`${key}: ${value}`, 20, y);
      y += 10;
    });
  }
}

interface ImageExportOptions {
  width?: number;
  height?: number;
  quality?: number;
  backgroundColor?: string;
}

interface SVGExportOptions {
  width?: number;
  height?: number;
  includeStyles?: boolean;
}

interface PDFExportOptions {
  includeMetadata?: boolean;
  metadata?: Record<string, any>;
}
```

### Solution 3: Export UI Component
```typescript
// src/components/ExportMenu.tsx
import React, { useState } from 'react';
import { GraphExporter, ImageExporter } from '../utils/exportUtils';

interface ExportMenuProps {
  graphData: GraphData;
  canvasRef: React.RefObject<HTMLCanvasElement>;
  selectedNodes?: string[];
}

export const ExportMenu: React.FC<ExportMenuProps> = ({
  graphData,
  canvasRef,
  selectedNodes = []
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [isExporting, setIsExporting] = useState(false);
  const [exportFormat, setExportFormat] = useState<'csv' | 'json' | 'graphml' | 'png' | 'svg' | 'pdf'>('csv');
  const [exportOptions, setExportOptions] = useState({
    selectedOnly: false,
    includeStats: true,
    imageQuality: 1.0,
    imageWidth: 1920,
    imageHeight: 1080
  });
  
  const handleExport = async () => {
    setIsExporting(true);
    
    try {
      const exporter = new GraphExporter(graphData);
      const imageExporter = new ImageExporter(canvasRef);
      
      switch (exportFormat) {
        case 'csv':
          const csvData = exporter.exportNodesAsCSV(exportOptions.selectedOnly);
          downloadFile(csvData, 'graph-nodes.csv', 'text/csv');
          
          const edgesCsvData = exporter.exportEdgesAsCSV(exportOptions.selectedOnly);
          downloadFile(edgesCsvData, 'graph-edges.csv', 'text/csv');
          break;
          
        case 'json':
          const jsonData = exporter.exportGraphAsJSON({
            selectedOnly: exportOptions.selectedOnly,
            includeStats: exportOptions.includeStats
          });
          downloadFile(jsonData, 'graph-data.json', 'application/json');
          break;
          
        case 'graphml':
          const graphmlData = exporter.exportGraphML();
          downloadFile(graphmlData, 'graph-data.graphml', 'application/xml');
          break;
          
        case 'png':
          await imageExporter.exportAsPNG({
            width: exportOptions.imageWidth,
            height: exportOptions.imageHeight,
            quality: exportOptions.imageQuality
          });
          break;
          
        case 'svg':
          await imageExporter.exportAsSVG({
            width: exportOptions.imageWidth,
            height: exportOptions.imageHeight
          });
          break;
          
        case 'pdf':
          await imageExporter.exportAsPDF({
            includeMetadata: true,
            metadata: {
              'Total Nodes': graphData.nodes.length,
              'Total Edges': graphData.edges.length,
              'Selected Nodes': exportOptions.selectedOnly ? selectedNodes.length : 'All'
            }
          });
          break;
      }
    } catch (error) {
      console.error('Export failed:', error);
      alert('Export failed. Please try again.');
    } finally {
      setIsExporting(false);
      setIsOpen(false);
    }
  };
  
  const downloadFile = (content: string, filename: string, mimeType: string) => {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };
  
  return (
    <div className="relative">
      <Button
        variant="outline"
        size="sm"
        onClick={() => setIsOpen(!isOpen)}
        disabled={isExporting}
        aria-label="Export graph data"
      >
        {isExporting ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : (
          <Download className="h-4 w-4" />
        )}
      </Button>
      
      {isOpen && (
        <div className="absolute top-full right-0 mt-2 w-80 bg-white dark:bg-gray-800 border rounded-lg shadow-lg p-4 z-50">
          <h3 className="font-semibold mb-3">Export Graph</h3>
          
          {/* Format Selection */}
          <div className="mb-4">
            <label className="block text-sm font-medium mb-2">Format</label>
            <select
              value={exportFormat}
              onChange={(e) => setExportFormat(e.target.value as any)}
              className="w-full p-2 border rounded"
            >
              <optgroup label="Data Formats">
                <option value="csv">CSV (Nodes + Edges)</option>
                <option value="json">JSON</option>
                <option value="graphml">GraphML</option>
              </optgroup>
              <optgroup label="Image Formats">
                <option value="png">PNG Image</option>
                <option value="svg">SVG Vector</option>
                <option value="pdf">PDF Report</option>
              </optgroup>
            </select>
          </div>
          
          {/* Export Options */}
          <div className="space-y-3 mb-4">
            <label className="flex items-center">
              <input
                type="checkbox"
                checked={exportOptions.selectedOnly}
                onChange={(e) => setExportOptions(prev => ({
                  ...prev,
                  selectedOnly: e.target.checked
                }))}
                className="mr-2"
              />
              <span className="text-sm">Selected nodes only</span>
            </label>
            
            {['csv', 'json'].includes(exportFormat) && (
              <label className="flex items-center">
                <input
                  type="checkbox"
                  checked={exportOptions.includeStats}
                  onChange={(e) => setExportOptions(prev => ({
                    ...prev,
                    includeStats: e.target.checked
                  }))}
                  className="mr-2"
                />
                <span className="text-sm">Include statistics</span>
              </label>
            )}
            
            {['png', 'svg', 'pdf'].includes(exportFormat) && (
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-gray-600">Width</label>
                  <input
                    type="number"
                    value={exportOptions.imageWidth}
                    onChange={(e) => setExportOptions(prev => ({
                      ...prev,
                      imageWidth: parseInt(e.target.value)
                    }))}
                    className="w-full p-1 border rounded text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-600">Height</label>
                  <input
                    type="number"
                    value={exportOptions.imageHeight}
                    onChange={(e) => setExportOptions(prev => ({
                      ...prev,
                      imageHeight: parseInt(e.target.value)
                    }))}
                    className="w-full p-1 border rounded text-sm"
                  />
                </div>
              </div>
            )}
          </div>
          
          {/* Export Button */}
          <div className="flex justify-between">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsOpen(false)}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              onClick={handleExport}
              disabled={isExporting}
            >
              {isExporting ? 'Exporting...' : 'Export'}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};
```

### Solution 4: Configuration Export/Import
```typescript
// src/utils/configurationExport.ts
export class ConfigurationManager {
  exportConfiguration(config: GraphConfiguration): string {
    const exportData = {
      metadata: {
        version: '1.0',
        exportedAt: new Date().toISOString(),
        type: 'graph-configuration'
      },
      configuration: {
        appearance: {
          nodeColors: config.nodeTypeColors,
          linkColor: config.linkColor,
          backgroundColor: config.backgroundColor,
          showLabels: config.showLabels,
          labelSize: config.labelSize
        },
        physics: {
          friction: config.friction,
          linkSpring: config.linkSpring,
          repulsion: config.repulsion,
          gravity: config.gravity
        },
        sizing: {
          sizeMapping: config.sizeMapping,
          minNodeSize: config.minNodeSize,
          maxNodeSize: config.maxNodeSize,
          sizeMultiplier: config.sizeMultiplier
        },
        visibility: {
          nodeTypeVisibility: config.nodeTypeVisibility,
          showCurvedLinks: config.curvedLinks
        }
      }
    };
    
    return JSON.stringify(exportData, null, 2);
  }
  
  importConfiguration(configJson: string): GraphConfiguration {
    try {
      const importData = JSON.parse(configJson);
      
      if (importData.metadata?.type !== 'graph-configuration') {
        throw new Error('Invalid configuration file format');
      }
      
      // Validate and merge with defaults
      const config = importData.configuration;
      return {
        // Map imported config back to application config format
        nodeTypeColors: config.appearance.nodeColors,
        linkColor: config.appearance.linkColor,
        backgroundColor: config.appearance.backgroundColor,
        showLabels: config.appearance.showLabels,
        labelSize: config.appearance.labelSize,
        friction: config.physics.friction,
        linkSpring: config.physics.linkSpring,
        repulsion: config.physics.repulsion,
        gravity: config.physics.gravity,
        sizeMapping: config.sizing.sizeMapping,
        minNodeSize: config.sizing.minNodeSize,
        maxNodeSize: config.sizing.maxNodeSize,
        sizeMultiplier: config.sizing.sizeMultiplier,
        nodeTypeVisibility: config.visibility.nodeTypeVisibility,
        curvedLinks: config.visibility.showCurvedLinks
      };
    } catch (error) {
      throw new Error(`Failed to import configuration: ${error.message}`);
    }
  }
}
```

## Recommended Solution
**Combination of all solutions**: Implement comprehensive export system with data export, image export, UI components, and configuration management.

### Benefits
- **Data Portability**: Users can extract and use data in other tools
- **Reporting**: Professional-quality exports for presentations and publications  
- **Workflow Integration**: Fits into existing data analysis pipelines
- **Collaboration**: Easy sharing of views, configurations, and results

## Implementation Plan

### Phase 1: Data Export Foundation (3-4 hours)
1. Create GraphExporter utility class
2. Implement CSV, JSON, and GraphML export formats
3. Add basic file download functionality

### Phase 2: Image Export Capabilities (2-3 hours)
1. Create ImageExporter utility class
2. Implement PNG, SVG, and PDF export
3. Add export options and quality settings

### Phase 3: Export UI Integration (2-3 hours)
1. Create ExportMenu component
2. Add export button to ControlPanel
3. Implement export options interface

### Phase 4: Configuration Management (1-2 hours)
1. Add configuration export/import functionality
2. Create view state persistence
3. Add sharing capabilities for configurations

## Testing Strategy
1. **Format Testing**: Verify all export formats work correctly
2. **Data Integrity**: Ensure exported data maintains accuracy
3. **File Compatibility**: Test exported files in other applications
4. **Performance Testing**: Test export performance with large datasets

## Priority Justification
This is Low Priority because:
- **Core Functionality**: Application works well for visualization without export
- **User Segment**: Export features benefit specific workflows but not all users
- **Development Scope**: Significant implementation effort for secondary feature
- **Workarounds**: Users can screenshot or manually extract data if needed

## Related Issues
- [Issue #012: Hardcoded Mock Data](../medium/012-hardcoded-mock-data.md)
- [Issue #028: Documentation Gaps](./028-documentation-gaps.md)
- [Issue #021: Incomplete Error Handling](./021-incomplete-error-handling.md)

## Dependencies
- File download utilities
- Image generation libraries (jsPDF, etc.)
- CSV/JSON serialization
- Canvas-to-image conversion
- GraphML specification compliance

## Estimated Fix Time
**8-10 hours** for implementing comprehensive export system with multiple formats and proper UI integration