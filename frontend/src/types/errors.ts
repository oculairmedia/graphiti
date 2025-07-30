// Error handling types and utilities

export type GraphError = Error | { message: string; code?: string };

export function isGraphError(error: unknown): error is GraphError {
  return error instanceof Error || 
    (typeof error === 'object' && error !== null && 'message' in error);
}

export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === 'object' && error !== null && 'message' in error) {
    return String((error as { message: unknown }).message);
  }
  if (typeof error === 'string') {
    return error;
  }
  return 'Unknown error occurred';
}

export function logError(context: string, error: unknown): void {
  const message = getErrorMessage(error);
  console.error(`[${context}] ${message}`, error);
}

// Specific error types
export class GraphDataError extends Error {
  constructor(message: string, public code?: string) {
    super(message);
    this.name = 'GraphDataError';
  }
}

export class ConfigurationError extends Error {
  constructor(message: string, public code?: string) {
    super(message);
    this.name = 'ConfigurationError';
  }
}

export class NetworkError extends Error {
  constructor(message: string, public statusCode?: number) {
    super(message);
    this.name = 'NetworkError';
  }
}

export class StorageError extends Error {
  constructor(message: string, public code?: string) {
    super(message);
    this.name = 'StorageError';
  }
}

// Type guards
export function isNetworkError(error: unknown): error is NetworkError {
  return error instanceof NetworkError;
}

export function isStorageError(error: unknown): error is StorageError {
  return error instanceof StorageError;
}

export function isQuotaExceededError(error: unknown): boolean {
  return error instanceof Error && error.name === 'QuotaExceededError';
}