"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import asyncio
import logging
import os
from typing import Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)


class RustCentralityClient:
    """
    Client for communicating with the Rust centrality service.
    
    This client provides the same interface as the Python centrality functions
    but routes requests to the high-performance Rust service.
    """
    
    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize the Rust centrality client.
        
        Args:
            base_url: Base URL of the Rust centrality service
        """
        self.base_url = base_url or os.getenv("RUST_CENTRALITY_URL", "http://localhost:3001")
        self.timeout = aiohttp.ClientTimeout(total=300)  # 5 minute timeout
        
        logger.info(f"Initialized Rust centrality client with base URL: {self.base_url}")
    
    async def calculate_pagerank(
        self,
        damping_factor: float = 0.85,
        iterations: int = 20,
        group_id: Optional[str] = None,
        store_results: bool = False,
    ) -> Dict[str, float]:
        """
        Calculate PageRank centrality using the Rust service.
        
        Args:
            damping_factor: Probability of following an edge (default 0.85)
            iterations: Number of iterations for convergence (default 20)
            group_id: Optional group ID to filter nodes
            store_results: Whether to store results in database
            
        Returns:
            Dictionary mapping node UUIDs to PageRank scores
        """
        payload = {
            "damping_factor": damping_factor,
            "iterations": iterations,
            "group_id": group_id,
            "store_results": store_results,
        }
        
        response = await self._make_request("/centrality/pagerank", payload)
        return response["scores"]
    
    async def calculate_degree_centrality(
        self,
        direction: str = "both",
        group_id: Optional[str] = None,
        store_results: bool = False,
    ) -> Dict[str, Dict[str, int]]:
        """
        Calculate degree centrality using the Rust service.
        
        Args:
            direction: "in", "out", or "both" for edge direction
            group_id: Optional group ID to filter nodes
            store_results: Whether to store results in database
            
        Returns:
            Dictionary mapping node UUIDs to degree counts
        """
        payload = {
            "direction": direction,
            "group_id": group_id,
            "store_results": store_results,
        }
        
        response = await self._make_request("/centrality/degree", payload)
        
        # Convert flat scores back to the expected format
        degrees = {}
        for uuid, score in response["scores"].items():
            if direction == "both":
                degrees[uuid] = {"total": int(score)}
            elif direction == "in":
                degrees[uuid] = {"in": int(score)}
            else:  # out
                degrees[uuid] = {"out": int(score)}
        
        return degrees
    
    async def calculate_betweenness_centrality(
        self,
        sample_size: Optional[int] = None,
        group_id: Optional[str] = None,
        store_results: bool = False,
    ) -> Dict[str, float]:
        """
        Calculate betweenness centrality using the Rust service.
        
        Args:
            sample_size: Number of nodes to sample (None for all nodes)
            group_id: Optional group ID to filter nodes
            store_results: Whether to store results in database
            
        Returns:
            Dictionary mapping node UUIDs to betweenness scores
        """
        payload = {
            "sample_size": sample_size,
            "group_id": group_id,
            "store_results": store_results,
        }
        
        response = await self._make_request("/centrality/betweenness", payload)
        return response["scores"]
    
    async def calculate_all_centralities(
        self,
        group_id: Optional[str] = None,
        store_results: bool = True,
    ) -> Dict[str, Dict[str, float]]:
        """
        Calculate all centrality metrics using the Rust service.
        
        Args:
            group_id: Optional group ID to filter nodes
            store_results: Whether to store results in the database
            
        Returns:
            Dictionary mapping node UUIDs to all centrality scores
        """
        payload = {
            "group_id": group_id,
            "store_results": store_results,
        }
        
        response = await self._make_request("/centrality/all", payload)
        return response["scores"]
    
    async def get_stats(self) -> Dict[str, int]:
        """
        Get basic graph statistics from the Rust service.
        
        Returns:
            Dictionary with graph statistics
        """
        return await self._make_request("/stats", method="GET")
    
    async def health_check(self) -> Dict[str, str]:
        """
        Check the health of the Rust service.
        
        Returns:
            Dictionary with health status
        """
        return await self._make_request("/health", method="GET")
    
    async def _make_request(
        self, 
        endpoint: str, 
        payload: Optional[Dict] = None, 
        method: str = "POST"
    ) -> Dict:
        """
        Make an HTTP request to the Rust service.
        
        Args:
            endpoint: API endpoint path
            payload: Request payload for POST requests
            method: HTTP method (GET or POST)
            
        Returns:
            Response data as dictionary
            
        Raises:
            Exception: If the request fails
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                if method == "GET":
                    async with session.get(url) as response:
                        return await self._handle_response(response, endpoint)
                else:  # POST
                    async with session.post(url, json=payload) as response:
                        return await self._handle_response(response, endpoint)
                        
        except asyncio.TimeoutError:
            logger.error(f"Timeout when calling Rust service endpoint: {endpoint}")
            raise Exception(f"Rust centrality service timeout: {endpoint}")
        except aiohttp.ClientError as e:
            logger.error(f"HTTP error when calling Rust service: {e}")
            raise Exception(f"Rust centrality service error: {e}")
        except Exception as e:
            logger.error(f"Unexpected error when calling Rust service: {e}")
            raise Exception(f"Rust centrality service error: {e}")
    
    async def _handle_response(self, response: aiohttp.ClientResponse, endpoint: str) -> Dict:
        """
        Handle HTTP response from the Rust service.
        
        Args:
            response: HTTP response object
            endpoint: API endpoint for error context
            
        Returns:
            Response data as dictionary
            
        Raises:
            Exception: If the response indicates an error
        """
        if response.status == 200:
            data = await response.json()
            logger.debug(f"Rust service {endpoint} succeeded: {len(str(data))} bytes")
            return data
        else:
            error_text = await response.text()
            logger.error(f"Rust service {endpoint} failed: {response.status} - {error_text}")
            raise Exception(f"Rust centrality service error {response.status}: {error_text}")