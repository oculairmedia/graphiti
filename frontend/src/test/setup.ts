// Vitest Setup File
import '@testing-library/jest-dom';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeAll, afterAll, vi } from 'vitest';
import React from 'react';

// Mock localStorage with proper implementation
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (key: string) => store[key] || null,
    setItem: (key: string, value: string) => {
      store[key] = value.toString();
    },
    removeItem: (key: string) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
    get length() {
      return Object.keys(store).length;
    },
    key: (index: number) => {
      const keys = Object.keys(store);
      return keys[index] || null;
    },
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock,
  writable: true,
});

// Cleanup after each test
afterEach(() => {
  cleanup();
});

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

// Mock IntersectionObserver
global.IntersectionObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock ResizeObserver
global.ResizeObserver = vi.fn().mockImplementation(() => ({
  observe: vi.fn(),
  unobserve: vi.fn(),
  disconnect: vi.fn(),
}));

// Mock requestAnimationFrame
global.requestAnimationFrame = vi.fn((cb) => setTimeout(cb, 0));
global.cancelAnimationFrame = vi.fn((id) => clearTimeout(id));

// localStorage is already mocked above at line 7-34

// Mock IndexedDB
global.indexedDB = {
  open: vi.fn().mockReturnValue({
    onsuccess: null,
    onerror: null,
    onupgradeneeded: null,
    result: {
      objectStoreNames: { contains: vi.fn(() => false) },
      createObjectStore: vi.fn(),
      close: vi.fn(),
    },
  }),
  deleteDatabase: vi.fn(),
  databases: vi.fn().mockResolvedValue([]),
  cmp: vi.fn(),
} as any;

// Mock WebSocket
class WebSocketMock {
  url: string;
  readyState: number = 0;
  onopen: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  
  constructor(url: string) {
    this.url = url;
    setTimeout(() => {
      this.readyState = 1;
      if (this.onopen) this.onopen(new Event('open'));
    }, 0);
  }
  
  send = vi.fn();
  close = vi.fn(() => {
    this.readyState = 3;
    if (this.onclose) this.onclose(new CloseEvent('close'));
  });
}

global.WebSocket = WebSocketMock as any;

// Mock fetch for API requests
global.fetch = vi.fn().mockImplementation((url: string) => {
  // Default response for graph data endpoint
  if (url.includes('/api/visualize')) {
    const responseData = {
      data: {
        nodes: [],
        edges: [],
      },
    };
    return Promise.resolve({
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: new Headers(),
      json: () => Promise.resolve(responseData),
      text: () => Promise.resolve(JSON.stringify(responseData)),
      clone: () => ({ ok: true, status: 200 }),
    });
  }
  
  // Default response for stats endpoint
  if (url.includes('/api/stats')) {
    return Promise.resolve({
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: new Headers(),
      json: () => Promise.resolve({
        node_count: 0,
        edge_count: 0,
      }),
      text: () => Promise.resolve(JSON.stringify({
        node_count: 0,
        edge_count: 0,
      })),
      clone: () => ({ ok: true, status: 200 }),
    });
  }
  
  // Default response for other endpoints
  return Promise.resolve({
    ok: true,
    status: 200,
    statusText: 'OK',
    headers: new Headers(),
    json: () => Promise.resolve({}),
    text: () => Promise.resolve('{}'),
    clone: () => ({ ok: true, status: 200 }),
  });
}) as any;

// Mock DuckDB WASM
vi.mock('@duckdb/duckdb-wasm', () => {
  const mockBundle = {
    mainModule: '/duckdb.wasm',
    mainWorker: '/worker.js',
  };
  
  return {
    selectDuckDBPlatform: vi.fn().mockResolvedValue(mockBundle),
    selectBundle: vi.fn().mockResolvedValue(mockBundle),
    getJsDelivrBundles: vi.fn().mockReturnValue(mockBundle), // Note: This should return immediately, not a promise
    instantiate: vi.fn(),
    initializeDuckDB: vi.fn().mockResolvedValue({
      connect: vi.fn().mockResolvedValue({
        query: vi.fn().mockResolvedValue({ 
          toArray: () => [],
          numRows: 0,
          numCols: 0,
        }),
        close: vi.fn(),
        prepare: vi.fn(),
        insertArrowFromIPCStream: vi.fn(),
        insertArrowTable: vi.fn(),
      }),
      registerFileHandle: vi.fn(),
      registerFileURL: vi.fn(),
      registerFileBuffer: vi.fn(),
      dropFile: vi.fn(),
      dropFiles: vi.fn(),
      open: vi.fn(),
      reset: vi.fn(),
      getVersion: vi.fn().mockReturnValue('0.10.2'),
      tokenize: vi.fn(),
    }),
    DuckDBWorker: vi.fn(),
    DuckDBNode: vi.fn(),
    AsyncDuckDB: vi.fn(),
    DuckDBDataProtocol: {},
    ConsoleLogger: vi.fn(),
    VoidLogger: vi.fn(),
    createLogger: vi.fn(),
  };
});

// Mock Cosmograph
vi.mock('@cosmograph/react', () => ({
  Cosmograph: vi.fn(({ children }) => children),
  useCosmograph: vi.fn(() => ({
    fitView: vi.fn(),
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
    selectNodes: vi.fn(),
  })),
}));

// Mock IDB library
vi.mock('idb', () => ({
  openDB: vi.fn().mockResolvedValue({
    get: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    clear: vi.fn(),
    getAllKeys: vi.fn().mockResolvedValue([]),
    getAll: vi.fn().mockResolvedValue([]),
    transaction: vi.fn(),
    close: vi.fn(),
  }),
  deleteDB: vi.fn(),
}));

// Mock react-router-dom
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useLocation: () => ({ pathname: '/', search: '', hash: '', state: null }),
    useParams: () => ({}),
  };
});

// Mock ParallelInitProvider to bypass complex initialization in tests
vi.mock('../contexts/ParallelInitProvider', () => ({
  ParallelInitProvider: ({ children }: { children: React.ReactNode }) => children,
  useParallelInit: () => ({
    initialized: true,
    progress: 100,
    error: null,
    initializationSteps: [],
  }),
}));

// Mock LoadingCoordinator
vi.mock('../contexts/LoadingCoordinator', () => ({
  LoadingCoordinatorProvider: ({ children }: { children: React.ReactNode }) => children,
  useLoadingCoordinator: () => ({
    setInitialized: vi.fn(),
    setError: vi.fn(),
    resetError: vi.fn(),
    isInitialized: true,
    error: null,
    updateStage: vi.fn(),
    updateStatus: vi.fn(),
    completeStage: vi.fn(),
    setStageComplete: vi.fn(),
    getStageStatus: vi.fn(() => 'complete'),
    isStageComplete: vi.fn().mockReturnValue(false),
    getStageProgress: vi.fn().mockReturnValue(0),
    stages: {},
  }),
}));

// Mock useDuckDBService hook
vi.mock('../hooks/useDuckDBService', () => ({
  useDuckDBService: () => ({
    service: {
      query: vi.fn().mockResolvedValue({ toArray: () => [] }),
      insertData: vi.fn(),
      updateData: vi.fn(),
      deleteData: vi.fn(),
      initializeTables: vi.fn(),
    },
    isInitialized: false,
    isLoading: false,
    error: null,
    stats: null,
    duckdb: null,
    connection: null,
    getDuckDBConnection: vi.fn().mockReturnValue(null),
    // Add properties expected by tests
    initialized: false,
    executeQuery: vi.fn().mockResolvedValue([]),
    initializeTables: vi.fn(),
    insertData: vi.fn(),
    updateData: vi.fn(),
    deleteData: vi.fn(),
  }),
}));

// Mock useWebSocket hook 
vi.mock('../hooks/useWebSocket', () => ({
  useWebSocket: ({ onMessage, onConnect, onDisconnect, onError }: any) => {
    // Simulate connection after a delay
    setTimeout(() => {
      if (onConnect) onConnect();
    }, 100);
    
    return {
      isConnected: false,
      connectionQuality: 'good' as const,
      latency: 0,
    };
  },
  NodeAccessEvent: {},
  GraphUpdateEvent: {},
  DeltaUpdateEvent: {},
  CacheInvalidateEvent: {},
  WebSocketEvent: {},
}));

// Setup test environment variables
beforeAll(() => {
  process.env.VITE_API_BASE_URL = 'http://localhost:8000';
  process.env.VITE_WS_URL = 'ws://localhost:8003/ws';
  process.env.VITE_RUST_WS_URL = 'ws://localhost:3000/ws';
  process.env.VITE_WEBSOCKET_URL = 'ws://localhost:8003/ws';
});

afterAll(() => {
  vi.clearAllMocks();
});