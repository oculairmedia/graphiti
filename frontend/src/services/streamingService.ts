/**
 * Streaming data pipeline for progressive graph loading
 * Handles chunked Arrow data and incremental rendering
 */

import * as arrow from 'apache-arrow';
import { logger } from '../utils/logger';
import { GraphNode } from '../api/types';
import { GraphLink } from '../types/graph';

interface StreamChunk {
  nodes?: GraphNode[];
  edges?: GraphLink[];
  metadata?: {
    chunkIndex: number;
    totalChunks: number;
    timestamp: number;
  };
}

interface StreamOptions {
  chunkSize?: number;
  onChunk?: (chunk: StreamChunk) => void;
  onProgress?: (progress: number) => void;
  onComplete?: () => void;
  onError?: (error: Error) => void;
}

export class StreamingService {
  private abortController: AbortController | null = null;
  private reader: ReadableStreamDefaultReader<Uint8Array> | null = null;
  private buffer: Uint8Array = new Uint8Array(0);
  private processedChunks = 0;
  private totalChunks = 0;
  
  /**
   * Stream Arrow data from URL
   */
  async streamArrowData(
    url: string,
    options: StreamOptions = {}
  ): Promise<void> {
    const {
      chunkSize = 1024 * 1024, // 1MB chunks
      onChunk,
      onProgress,
      onComplete,
      onError
    } = options;

    try {
      // Create abort controller for cancellation
      this.abortController = new AbortController();
      
      // Fetch with streaming support
      const response = await fetch(url, {
        signal: this.abortController.signal,
        headers: {
          'Accept': 'application/octet-stream'
        }
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      if (!response.body) {
        throw new Error('Response body is null');
      }

      // Get total size if available
      const contentLength = response.headers.get('content-length');
      const totalSize = contentLength ? parseInt(contentLength, 10) : 0;
      
      // Create reader
      this.reader = response.body.getReader();
      
      let receivedLength = 0;
      const chunks: Uint8Array[] = [];
      
      // Read stream
      while (true) {
        const { done, value } = await this.reader.read();
        
        if (done) break;
        
        chunks.push(value);
        receivedLength += value.length;
        
        // Report progress
        if (onProgress && totalSize > 0) {
          const progress = (receivedLength / totalSize) * 100;
          onProgress(progress);
        }
        
        // Process chunk if we have enough data
        if (receivedLength >= chunkSize || done) {
          const chunkData = this.mergeChunks(chunks);
          chunks.length = 0;
          receivedLength = 0;
          
          // Process Arrow data chunk
          const processedChunk = await this.processArrowChunk(chunkData);
          
          if (processedChunk && onChunk) {
            this.processedChunks++;
            onChunk({
              ...processedChunk,
              metadata: {
                chunkIndex: this.processedChunks,
                totalChunks: this.totalChunks || 1,
                timestamp: Date.now()
              }
            });
          }
        }
      }
      
      // Process any remaining data
      if (chunks.length > 0) {
        const finalChunk = this.mergeChunks(chunks);
        const processedChunk = await this.processArrowChunk(finalChunk);
        
        if (processedChunk && onChunk) {
          this.processedChunks++;
          onChunk({
            ...processedChunk,
            metadata: {
              chunkIndex: this.processedChunks,
              totalChunks: this.totalChunks || 1,
              timestamp: Date.now()
            }
          });
        }
      }
      
      if (onComplete) {
        onComplete();
      }
      
      logger.log('[StreamingService] Streaming completed', {
        processedChunks: this.processedChunks,
        totalSize
      });
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        logger.log('[StreamingService] Stream aborted');
      } else {
        logger.error('[StreamingService] Stream error:', error);
        if (onError) {
          onError(error as Error);
        }
      }
    } finally {
      this.cleanup();
    }
  }

  /**
   * Stream from ReadableStream directly
   */
  async streamFromReadable(
    stream: ReadableStream<Uint8Array>,
    options: StreamOptions = {}
  ): Promise<void> {
    const { onChunk, onProgress, onComplete, onError } = options;
    
    try {
      this.reader = stream.getReader();
      let processedBytes = 0;
      
      while (true) {
        const { done, value } = await this.reader.read();
        
        if (done) break;
        
        // Append to buffer
        this.appendToBuffer(value);
        processedBytes += value.length;
        
        // Try to process Arrow records from buffer
        const records = this.extractArrowRecords();
        
        for (const record of records) {
          const chunk = this.transformArrowRecord(record);
          if (chunk && onChunk) {
            this.processedChunks++;
            onChunk({
              ...chunk,
              metadata: {
                chunkIndex: this.processedChunks,
                totalChunks: 0, // Unknown in stream mode
                timestamp: Date.now()
              }
            });
          }
        }
        
        if (onProgress) {
          // Estimate progress based on chunks
          onProgress(this.processedChunks);
        }
      }
      
      // Process any remaining buffer
      const finalRecords = this.extractArrowRecords(true);
      for (const record of finalRecords) {
        const chunk = this.transformArrowRecord(record);
        if (chunk && onChunk) {
          this.processedChunks++;
          onChunk({
            ...chunk,
            metadata: {
              chunkIndex: this.processedChunks,
              totalChunks: this.processedChunks,
              timestamp: Date.now()
            }
          });
        }
      }
      
      if (onComplete) {
        onComplete();
      }
    } catch (error) {
      logger.error('[StreamingService] ReadableStream error:', error);
      if (onError) {
        onError(error as Error);
      }
    } finally {
      this.cleanup();
    }
  }

  /**
   * Process DuckDB query results as stream
   */
  async streamDuckDBQuery(
    connection: any,
    query: string,
    options: StreamOptions = {}
  ): Promise<void> {
    const { onChunk, onProgress, onComplete, onError } = options;
    
    try {
      // Execute streaming query
      const stream = await connection.stream(query);
      const batchSize = 1000;
      let batch: any[] = [];
      let totalProcessed = 0;
      
      for await (const row of stream) {
        batch.push(row);
        
        if (batch.length >= batchSize) {
          const chunk = this.processDuckDBBatch(batch);
          if (chunk && onChunk) {
            this.processedChunks++;
            onChunk({
              ...chunk,
              metadata: {
                chunkIndex: this.processedChunks,
                totalChunks: 0,
                timestamp: Date.now()
              }
            });
          }
          
          totalProcessed += batch.length;
          if (onProgress) {
            onProgress(totalProcessed);
          }
          
          batch = [];
        }
      }
      
      // Process remaining batch
      if (batch.length > 0) {
        const chunk = this.processDuckDBBatch(batch);
        if (chunk && onChunk) {
          this.processedChunks++;
          onChunk({
            ...chunk,
            metadata: {
              chunkIndex: this.processedChunks,
              totalChunks: this.processedChunks,
              timestamp: Date.now()
            }
          });
        }
      }
      
      if (onComplete) {
        onComplete();
      }
      
      logger.log('[StreamingService] DuckDB streaming completed', {
        totalProcessed,
        chunks: this.processedChunks
      });
    } catch (error) {
      logger.error('[StreamingService] DuckDB stream error:', error);
      if (onError) {
        onError(error as Error);
      }
    }
  }

  /**
   * Abort active stream
   */
  abort(): void {
    if (this.abortController) {
      this.abortController.abort();
    }
    
    if (this.reader) {
      this.reader.cancel();
    }
    
    this.cleanup();
    logger.log('[StreamingService] Stream aborted');
  }

  /**
   * Get stream statistics
   */
  getStats(): {
    processedChunks: number;
    bufferSize: number;
    isStreaming: boolean;
  } {
    return {
      processedChunks: this.processedChunks,
      bufferSize: this.buffer.length,
      isStreaming: this.reader !== null
    };
  }

  // Private methods
  
  private mergeChunks(chunks: Uint8Array[]): Uint8Array {
    const totalLength = chunks.reduce((acc, chunk) => acc + chunk.length, 0);
    const merged = new Uint8Array(totalLength);
    let offset = 0;
    
    for (const chunk of chunks) {
      merged.set(chunk, offset);
      offset += chunk.length;
    }
    
    return merged;
  }

  private appendToBuffer(data: Uint8Array): void {
    const newBuffer = new Uint8Array(this.buffer.length + data.length);
    newBuffer.set(this.buffer);
    newBuffer.set(data, this.buffer.length);
    this.buffer = newBuffer;
  }

  private async processArrowChunk(data: Uint8Array): Promise<StreamChunk | null> {
    try {
      // Try to parse as Arrow IPC
      const table = arrow.tableFromIPC(data);
      const rows = table.toArray();
      
      // Determine if this is nodes or edges
      const schema = table.schema;
      const hasNodeFields = schema.fields.some(f => 
        f.name === 'node_type' || f.name === 'label'
      );
      
      if (hasNodeFields) {
        // Process as nodes
        return {
          nodes: rows.map((row: any) => ({
            id: row.id,
            label: row.label || row.name || row.id,
            node_type: row.node_type || 'Unknown',
            properties: row
          })),
          edges: []
        };
      } else {
        // Process as edges
        return {
          nodes: [],
          edges: rows.map((row: any) => ({
            source: row.source || row.from,
            target: row.target || row.to,
            edge_type: row.edge_type || 'RELATED',
            weight: row.weight || 1
          }))
        };
      }
    } catch (error) {
      // Not a complete Arrow record yet
      return null;
    }
  }

  private extractArrowRecords(flush = false): Uint8Array[] {
    const records: Uint8Array[] = [];
    
    // Arrow IPC has specific magic bytes and structure
    // For simplicity, we'll try to parse the entire buffer
    if (flush && this.buffer.length > 0) {
      records.push(this.buffer);
      this.buffer = new Uint8Array(0);
    }
    
    return records;
  }

  private transformArrowRecord(data: Uint8Array): StreamChunk | null {
    return this.processArrowChunk(data) as any;
  }

  private processDuckDBBatch(batch: any[]): StreamChunk {
    // Determine if batch contains nodes or edges
    if (batch.length === 0) {
      return { nodes: [], edges: [] };
    }
    
    const firstItem = batch[0];
    const hasNodeFields = 'node_type' in firstItem || 'label' in firstItem;
    
    if (hasNodeFields) {
      return {
        nodes: batch.map(row => ({
          id: row.id,
          label: row.label || row.name || row.id,
          node_type: row.node_type || 'Unknown',
          properties: row
        })),
        edges: []
      };
    } else {
      return {
        nodes: [],
        edges: batch.map(row => ({
          source: row.source || row.from,
          target: row.target || row.to,
          edge_type: row.edge_type || 'RELATED',
          weight: row.weight || 1
        }))
      };
    }
  }

  private cleanup(): void {
    this.abortController = null;
    this.reader = null;
    this.buffer = new Uint8Array(0);
  }
}

// Singleton instance
export const streamingService = new StreamingService();