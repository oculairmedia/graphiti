import { describe, it, expect, vi } from 'vitest'
import { graphitiClient } from '../../api/graphitiClient'

// Mock fetch
global.fetch = vi.fn()

describe('GraphitiClient Search API', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should call the correct search endpoint with proper format', async () => {
    // Mock successful response
    const mockResponse = {
      ok: true,
      json: async () => ({
        nodes: [
          {
            uuid: 'test-uuid',
            name: 'test-node',
            summary: 'test summary',
            labels: ['test'],
            group_id: 'test-group',
            created_at: '2023-01-01T00:00:00Z'
          }
        ]
      })
    }
    
    vi.mocked(fetch).mockResolvedValueOnce(mockResponse as Response)

    const query = {
      query: 'test search',
      max_nodes: 10,
      group_ids: ['test-group']
    }

    await graphitiClient.searchNodes(query)

    // Verify fetch was called with correct endpoint and format
    expect(fetch).toHaveBeenCalledWith(
      '/graphiti/search/nodes',
      expect.objectContaining({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(query)
      })
    )
  })

  it('should handle search errors gracefully', async () => {
    // Mock error response
    const mockResponse = {
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
      text: async () => 'Search service unavailable'
    }
    
    vi.mocked(fetch).mockResolvedValueOnce(mockResponse as Response)

    const query = {
      query: 'test search',
      max_nodes: 10
    }

    await expect(graphitiClient.searchNodes(query)).rejects.toThrow(
      'Graphiti API request failed: HTTP 500: Search service unavailable'
    )
  })

  it('should handle network errors', async () => {
    vi.mocked(fetch).mockRejectedValueOnce(new Error('Network error'))

    const query = {
      query: 'test search',
      max_nodes: 10
    }

    await expect(graphitiClient.searchNodes(query)).rejects.toThrow(
      'Graphiti API request failed: Network error'
    )
  })
})