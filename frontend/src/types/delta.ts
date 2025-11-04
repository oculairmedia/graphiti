/**
 * Delta update types for incremental graph updates
 */

export type DeltaType = 'incremental' | 'full' | 'snapshot';

export interface GraphDelta {
  sequence: number;
  timestamp: number;
  type: DeltaType;
  added_nodes?: any[];
  added_edges?: any[];
  updated_nodes?: any[];
  updated_edges?: any[];
  removed_nodes?: string[];
  removed_edges?: string[];
}

export interface DeltaOperation {
  type: 'add' | 'update' | 'remove';
  entity: 'node' | 'edge';
  data: any;
}
