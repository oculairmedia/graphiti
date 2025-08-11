import React, { ReactElement } from 'react';
import { render as rtlRender, RenderOptions } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { GraphConfigProvider } from '../contexts/GraphConfigProvider';
import { WebSocketProvider } from '../contexts/WebSocketProvider';
import { ParallelInitProvider } from '../contexts/ParallelInitProvider';
import { DuckDBProvider } from '../contexts/DuckDBProvider';
import { RustWebSocketProvider } from '../contexts/RustWebSocketProvider';
import { LoadingCoordinatorProvider } from '../contexts/LoadingCoordinator';

// Create a custom render function that includes all providers
function render(
  ui: ReactElement,
  {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    }),
    ...renderOptions
  }: RenderOptions & { queryClient?: QueryClient } = {}
) {
  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <ParallelInitProvider>
            <GraphConfigProvider>
              <LoadingCoordinatorProvider>
                <WebSocketProvider>
                  <DuckDBProvider>
                    <RustWebSocketProvider>
                      {children}
                    </RustWebSocketProvider>
                  </DuckDBProvider>
                </WebSocketProvider>
              </LoadingCoordinatorProvider>
            </GraphConfigProvider>
          </ParallelInitProvider>
        </BrowserRouter>
      </QueryClientProvider>
    );
  }

  return rtlRender(ui, { wrapper: Wrapper, ...renderOptions });
}

// Create mock data factories
export const createMockNode = (overrides = {}) => ({
  id: 'node-1',
  name: 'Test Node',
  node_type: 'Entity',
  summary: 'Test summary',
  created_at: '2024-01-01T00:00:00Z',
  properties: {
    degree_centrality: 0.5,
    pagerank_centrality: 0.3,
    eigenvector_centrality: 0.4,
    betweenness_centrality: 0.2,
  },
  x: 0,
  y: 0,
  ...overrides,
});

export const createMockEdge = (overrides = {}) => ({
  id: 'edge-1',
  from: 'node-1',
  to: 'node-2',
  relation_type: 'RELATED_TO',
  created_at: '2024-01-01T00:00:00Z',
  properties: {},
  ...overrides,
});

export const createMockLink = (overrides = {}) => ({
  source: 'node-1',
  target: 'node-2',
  ...overrides,
});

// Export everything from @testing-library/react
export * from '@testing-library/react';

// Import renderHook from @testing-library/react
import { renderHook as rtlRenderHook } from '@testing-library/react';

// Custom renderHook that uses our wrapper
export function renderHook<Result, Props>(
  render: (props: Props) => Result,
  options?: Omit<Parameters<typeof rtlRenderHook>[1], 'wrapper'> & { 
    queryClient?: QueryClient;
    wrapper?: React.ComponentType<{ children: React.ReactNode }>;
  }
) {
  const { queryClient, wrapper: customWrapper, ...restOptions } = options || {};
  
  // If a custom wrapper is provided, use it; otherwise use our default wrapper
  if (customWrapper) {
    return rtlRenderHook(render, { wrapper: customWrapper, ...restOptions });
  }
  
  // Use our default wrapper with all providers
  const WrapperComponent = ({ children }: { children: React.ReactNode }) => {
    const client = queryClient || new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
    
    return (
      <QueryClientProvider client={client}>
        <BrowserRouter>
          <ParallelInitProvider>
            <GraphConfigProvider>
              <LoadingCoordinatorProvider>
                <WebSocketProvider>
                  <DuckDBProvider>
                    <RustWebSocketProvider>
                      {children}
                    </RustWebSocketProvider>
                  </DuckDBProvider>
                </WebSocketProvider>
              </LoadingCoordinatorProvider>
            </GraphConfigProvider>
          </ParallelInitProvider>
        </BrowserRouter>
      </QueryClientProvider>
    );
  };
  
  return rtlRenderHook(render, { wrapper: WrapperComponent, ...restOptions });
}

// Export our custom render
export { render };