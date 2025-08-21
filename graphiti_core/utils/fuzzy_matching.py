"""
Configurable fuzzy matching system for entity deduplication.

This module provides configurable thresholds and strategies for fuzzy matching
during entity deduplication, allowing fine-tuning of similarity detection.
"""

import os
import logging
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


class MatchingStrategy(Enum):
    """Strategy for combining different matching approaches"""
    STRICT = "strict"        # High precision, low recall
    BALANCED = "balanced"    # Balanced precision/recall
    PERMISSIVE = "permissive"  # Low precision, high recall
    CUSTOM = "custom"        # Custom threshold configuration


class MatchingMode(Enum):
    """Mode for matching entities"""
    WORD_OVERLAP = "word_overlap"
    SEMANTIC_SIMILARITY = "semantic_similarity"
    COMBINED = "combined"


@dataclass
class FuzzyMatchingConfig:
    """Configuration for fuzzy matching parameters"""
    
    # Core similarity thresholds
    semantic_threshold: float = 0.8
    word_overlap_threshold: float = 0.6
    combined_threshold: float = 0.75
    
    # Edge matching thresholds (typically lower)
    edge_semantic_threshold: float = 0.6
    edge_word_overlap_threshold: float = 0.4
    edge_combined_threshold: float = 0.55
    
    # Name normalization thresholds  
    name_similarity_threshold: float = 0.85
    
    # Advanced matching options
    use_name_normalization: bool = True
    require_minimum_word_overlap: bool = True
    minimum_overlap_ratio: float = 0.3
    boost_exact_matches: bool = True
    
    # Performance settings
    max_candidates_per_entity: int = 100
    enable_early_stopping: bool = True
    
    @classmethod
    def from_strategy(cls, strategy: MatchingStrategy) -> 'FuzzyMatchingConfig':
        """Create configuration from predefined strategy"""
        if strategy == MatchingStrategy.STRICT:
            return cls(
                semantic_threshold=0.9,
                word_overlap_threshold=0.8,
                combined_threshold=0.85,
                edge_semantic_threshold=0.8,
                edge_word_overlap_threshold=0.6,
                edge_combined_threshold=0.7,
                name_similarity_threshold=0.9,
                minimum_overlap_ratio=0.5
            )
        elif strategy == MatchingStrategy.PERMISSIVE:
            return cls(
                semantic_threshold=0.6,
                word_overlap_threshold=0.4,
                combined_threshold=0.5,
                edge_semantic_threshold=0.5,
                edge_word_overlap_threshold=0.3,
                edge_combined_threshold=0.4,
                name_similarity_threshold=0.7,
                minimum_overlap_ratio=0.2
            )
        else:  # BALANCED (default)
            return cls()
    
    @classmethod
    def from_environment(cls) -> 'FuzzyMatchingConfig':
        """Load configuration from environment variables"""
        
        def get_float_env(key: str, default: float) -> float:
            try:
                return float(os.getenv(key, str(default)))
            except ValueError:
                logger.warning(f"Invalid float value for {key}, using default: {default}")
                return default
        
        def get_bool_env(key: str, default: bool) -> bool:
            return os.getenv(key, str(default)).lower() in ('true', '1', 'yes', 'on')
        
        def get_int_env(key: str, default: int) -> int:
            try:
                return int(os.getenv(key, str(default)))
            except ValueError:
                logger.warning(f"Invalid int value for {key}, using default: {default}")
                return default
        
        # Get strategy first
        strategy_name = os.getenv('FUZZY_MATCHING_STRATEGY', 'balanced').lower()
        try:
            strategy = MatchingStrategy(strategy_name)
            if strategy != MatchingStrategy.CUSTOM:
                config = cls.from_strategy(strategy)
            else:
                config = cls()
        except ValueError:
            logger.warning(f"Invalid strategy '{strategy_name}', using balanced")
            config = cls.from_strategy(MatchingStrategy.BALANCED)
        
        # Override with specific environment variables if present
        return cls(
            semantic_threshold=get_float_env('FUZZY_SEMANTIC_THRESHOLD', config.semantic_threshold),
            word_overlap_threshold=get_float_env('FUZZY_WORD_OVERLAP_THRESHOLD', config.word_overlap_threshold),
            combined_threshold=get_float_env('FUZZY_COMBINED_THRESHOLD', config.combined_threshold),
            edge_semantic_threshold=get_float_env('FUZZY_EDGE_SEMANTIC_THRESHOLD', config.edge_semantic_threshold),
            edge_word_overlap_threshold=get_float_env('FUZZY_EDGE_WORD_OVERLAP_THRESHOLD', config.edge_word_overlap_threshold),
            edge_combined_threshold=get_float_env('FUZZY_EDGE_COMBINED_THRESHOLD', config.edge_combined_threshold),
            name_similarity_threshold=get_float_env('FUZZY_NAME_SIMILARITY_THRESHOLD', config.name_similarity_threshold),
            use_name_normalization=get_bool_env('FUZZY_USE_NAME_NORMALIZATION', config.use_name_normalization),
            require_minimum_word_overlap=get_bool_env('FUZZY_REQUIRE_MIN_WORD_OVERLAP', config.require_minimum_word_overlap),
            minimum_overlap_ratio=get_float_env('FUZZY_MIN_OVERLAP_RATIO', config.minimum_overlap_ratio),
            boost_exact_matches=get_bool_env('FUZZY_BOOST_EXACT_MATCHES', config.boost_exact_matches),
            max_candidates_per_entity=get_int_env('FUZZY_MAX_CANDIDATES', config.max_candidates_per_entity),
            enable_early_stopping=get_bool_env('FUZZY_EARLY_STOPPING', config.enable_early_stopping)
        )


class FuzzyMatcher:
    """Configurable fuzzy matching engine for entity deduplication"""
    
    def __init__(self, config: Optional[FuzzyMatchingConfig] = None):
        self.config = config or FuzzyMatchingConfig.from_environment()
        logger.info(f"Initialized FuzzyMatcher with config: {self.config}")
    
    def calculate_word_overlap_similarity(self, text1: str, text2: str) -> float:
        """Calculate word overlap similarity between two texts"""
        if not text1 or not text2:
            return 0.0
        
        # Use name normalization if enabled
        if self.config.use_name_normalization:
            from graphiti_core.utils.uuid_utils import normalize_entity_name
            text1 = normalize_entity_name(text1)
            text2 = normalize_entity_name(text2)
        
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())
        
        if not words1 or not words2:
            return 0.0
        
        overlap = len(words1.intersection(words2))
        total = len(words1.union(words2))
        
        if total == 0:
            return 0.0
        
        similarity = overlap / total
        
        # Apply minimum overlap requirement
        if self.config.require_minimum_word_overlap:
            overlap_ratio = overlap / min(len(words1), len(words2))
            if overlap_ratio < self.config.minimum_overlap_ratio:
                return 0.0
        
        return similarity
    
    def calculate_semantic_similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """Calculate semantic similarity using embeddings"""
        if not embedding1 or not embedding2:
            return 0.0
        
        try:
            from graphiti_core.helpers import normalize_l2
            similarity = np.dot(normalize_l2(embedding1), normalize_l2(embedding2))
            return max(0.0, float(similarity))  # Ensure non-negative
        except Exception as e:
            logger.warning(f"Error calculating semantic similarity: {e}")
            return 0.0
    
    def calculate_combined_similarity(self, text1: str, text2: str, embedding1: List[float], embedding2: List[float]) -> float:
        """Calculate combined similarity using both word overlap and semantic similarity"""
        word_sim = self.calculate_word_overlap_similarity(text1, text2)
        semantic_sim = self.calculate_semantic_similarity(embedding1, embedding2)
        
        # Boost exact matches
        if self.config.boost_exact_matches and word_sim == 1.0:
            return 1.0
        
        # Weighted combination: semantic similarity gets more weight
        combined = 0.3 * word_sim + 0.7 * semantic_sim
        
        return combined
    
    def is_entity_match(self, entity1: Dict[str, Any], entity2: Dict[str, Any], mode: MatchingMode = MatchingMode.COMBINED) -> bool:
        """Determine if two entities are likely duplicates"""
        
        name1 = entity1.get('name', '')
        name2 = entity2.get('name', '')
        
        if not name1 or not name2:
            return False
        
        # Get embeddings
        embedding1 = entity1.get('name_embedding', [])
        embedding2 = entity2.get('name_embedding', [])
        
        if mode == MatchingMode.WORD_OVERLAP:
            similarity = self.calculate_word_overlap_similarity(name1, name2)
            threshold = self.config.word_overlap_threshold
        elif mode == MatchingMode.SEMANTIC_SIMILARITY:
            similarity = self.calculate_semantic_similarity(embedding1, embedding2)
            threshold = self.config.semantic_threshold
        else:  # COMBINED
            similarity = self.calculate_combined_similarity(name1, name2, embedding1, embedding2)
            threshold = self.config.combined_threshold
        
        return similarity >= threshold
    
    def is_edge_match(self, edge1: Dict[str, Any], edge2: Dict[str, Any], mode: MatchingMode = MatchingMode.COMBINED) -> bool:
        """Determine if two edges are likely duplicates"""
        
        # Edges must connect the same nodes
        if (edge1.get('source_node_uuid') != edge2.get('source_node_uuid') or
            edge1.get('target_node_uuid') != edge2.get('target_node_uuid')):
            return False
        
        fact1 = edge1.get('fact', '')
        fact2 = edge2.get('fact', '')
        
        if not fact1 or not fact2:
            return False
        
        # Get embeddings
        embedding1 = edge1.get('fact_embedding', [])
        embedding2 = edge2.get('fact_embedding', [])
        
        if mode == MatchingMode.WORD_OVERLAP:
            similarity = self.calculate_word_overlap_similarity(fact1, fact2)
            threshold = self.config.edge_word_overlap_threshold
        elif mode == MatchingMode.SEMANTIC_SIMILARITY:
            similarity = self.calculate_semantic_similarity(embedding1, embedding2)
            threshold = self.config.edge_semantic_threshold
        else:  # COMBINED
            similarity = self.calculate_combined_similarity(fact1, fact2, embedding1, embedding2)
            threshold = self.config.edge_combined_threshold
        
        return similarity >= threshold
    
    def find_entity_candidates(self, target_entity: Dict[str, Any], candidate_entities: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], float]]:
        """Find candidate matches for an entity with similarity scores"""
        
        matches = []
        target_name = target_entity.get('name', '')
        target_embedding = target_entity.get('name_embedding', [])
        
        if not target_name:
            return matches
        
        for candidate in candidate_entities:
            candidate_name = candidate.get('name', '')
            candidate_embedding = candidate.get('name_embedding', [])
            
            if not candidate_name:
                continue
            
            # Calculate combined similarity
            similarity = self.calculate_combined_similarity(
                target_name, candidate_name,
                target_embedding, candidate_embedding
            )
            
            if similarity >= self.config.combined_threshold:
                matches.append((candidate, similarity))
                
                # Early stopping if we have enough candidates
                if (self.config.enable_early_stopping and 
                    len(matches) >= self.config.max_candidates_per_entity):
                    break
        
        # Sort by similarity (highest first)
        matches.sort(key=lambda x: x[1], reverse=True)
        
        return matches[:self.config.max_candidates_per_entity]
    
    def find_edge_candidates(self, target_edge: Dict[str, Any], candidate_edges: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], float]]:
        """Find candidate matches for an edge with similarity scores"""
        
        matches = []
        target_fact = target_edge.get('fact', '')
        target_embedding = target_edge.get('fact_embedding', [])
        target_source = target_edge.get('source_node_uuid')
        target_target = target_edge.get('target_node_uuid')
        
        if not target_fact or not target_source or not target_target:
            return matches
        
        for candidate in candidate_edges:
            # Must connect same nodes
            if (candidate.get('source_node_uuid') != target_source or
                candidate.get('target_node_uuid') != target_target):
                continue
            
            candidate_fact = candidate.get('fact', '')
            candidate_embedding = candidate.get('fact_embedding', [])
            
            if not candidate_fact:
                continue
            
            # Calculate combined similarity
            similarity = self.calculate_combined_similarity(
                target_fact, candidate_fact,
                target_embedding, candidate_embedding
            )
            
            if similarity >= self.config.edge_combined_threshold:
                matches.append((candidate, similarity))
                
                # Early stopping if we have enough candidates
                if (self.config.enable_early_stopping and 
                    len(matches) >= self.config.max_candidates_per_entity):
                    break
        
        # Sort by similarity (highest first)
        matches.sort(key=lambda x: x[1], reverse=True)
        
        return matches[:self.config.max_candidates_per_entity]
    
    def get_similarity_stats(self, entities: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Get statistics about similarity thresholds and matching"""
        
        if len(entities) < 2:
            return {"error": "Need at least 2 entities for statistics"}
        
        word_similarities = []
        semantic_similarities = []
        combined_similarities = []
        
        # Calculate all pairwise similarities
        for i in range(len(entities)):
            for j in range(i + 1, len(entities)):
                entity1, entity2 = entities[i], entities[j]
                
                name1 = entity1.get('name', '')
                name2 = entity2.get('name', '')
                embedding1 = entity1.get('name_embedding', [])
                embedding2 = entity2.get('name_embedding', [])
                
                if name1 and name2:
                    word_sim = self.calculate_word_overlap_similarity(name1, name2)
                    word_similarities.append(word_sim)
                    
                    if embedding1 and embedding2:
                        semantic_sim = self.calculate_semantic_similarity(embedding1, embedding2)
                        semantic_similarities.append(semantic_sim)
                        
                        combined_sim = self.calculate_combined_similarity(name1, name2, embedding1, embedding2)
                        combined_similarities.append(combined_sim)
        
        def calc_stats(similarities):
            if not similarities:
                return {}
            return {
                "count": len(similarities),
                "min": min(similarities),
                "max": max(similarities),
                "mean": sum(similarities) / len(similarities),
                "above_threshold_count": len([s for s in similarities if s >= 0.8])
            }
        
        return {
            "config": self.config.__dict__,
            "word_overlap_stats": calc_stats(word_similarities),
            "semantic_similarity_stats": calc_stats(semantic_similarities),
            "combined_similarity_stats": calc_stats(combined_similarities),
            "total_pairs_analyzed": len(word_similarities)
        }


# Global matcher instance (can be reconfigured)
default_matcher = FuzzyMatcher()


def get_fuzzy_matcher(config: Optional[FuzzyMatchingConfig] = None) -> FuzzyMatcher:
    """Get a fuzzy matcher instance"""
    if config:
        return FuzzyMatcher(config)
    return default_matcher


def reconfigure_default_matcher(config: FuzzyMatchingConfig):
    """Reconfigure the default matcher"""
    global default_matcher
    default_matcher = FuzzyMatcher(config)


# Convenience functions for backward compatibility
def is_entity_fuzzy_match(entity1: Dict[str, Any], entity2: Dict[str, Any], threshold: Optional[float] = None) -> bool:
    """Check if two entities are fuzzy matches (backward compatibility)"""
    if threshold:
        # Create temporary config with custom threshold
        config = FuzzyMatchingConfig.from_environment()
        config.combined_threshold = threshold
        matcher = FuzzyMatcher(config)
    else:
        matcher = default_matcher
    
    return matcher.is_entity_match(entity1, entity2)


def is_edge_fuzzy_match(edge1: Dict[str, Any], edge2: Dict[str, Any], threshold: Optional[float] = None) -> bool:
    """Check if two edges are fuzzy matches (backward compatibility)"""
    if threshold:
        # Create temporary config with custom threshold
        config = FuzzyMatchingConfig.from_environment()
        config.edge_combined_threshold = threshold
        matcher = FuzzyMatcher(config)
    else:
        matcher = default_matcher
    
    return matcher.is_edge_match(edge1, edge2)