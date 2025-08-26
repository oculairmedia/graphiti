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

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from pathlib import Path


@dataclass
class SafetyConfig:
    """Safety configuration to prevent accidental writes"""
    require_explicit_dry_run: bool = True
    max_episodes_per_run: int = 1000
    max_runtime_minutes: int = 60
    allowed_databases: List[str] = field(default_factory=lambda: ['neo4j', 'default_db'])
    forbidden_query_patterns: List[str] = field(default_factory=lambda: [
        r'DROP\s+DATABASE',
        r'DELETE\s+.*\s+WHERE\s+.*\s+IS\s+NOT\s+NULL',  # Prevent mass deletion
        r'REMOVE\s+.*\s+WHERE\s+.*\s+IS\s+NOT\s+NULL',
    ])


@dataclass 
class DryRunConfig:
    """Configuration for dry-run benchmarking operations"""
    
    # Run identification
    run_id: Optional[str] = None
    description: str = ""
    
    # Data source configuration
    episodes_source: str = "database"  # "database", "file", "api"
    episodes_limit: Optional[int] = None
    episodes_filter: Dict[str, Any] = field(default_factory=dict)
    
    # Processing configuration
    batch_size: int = 10
    max_concurrent_episodes: int = 4
    enable_profiling: bool = True
    collect_memory_stats: bool = True
    
    # Hyperparameters to test
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    
    # Output configuration
    output_dir: Path = field(default_factory=lambda: Path("./dry_run_results"))
    export_formats: List[str] = field(default_factory=lambda: ["json", "csv"])
    save_detailed_metrics: bool = True
    
    # Safety configuration
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    
    # Performance monitoring
    profile_llm_calls: bool = True
    profile_embedding_calls: bool = True
    profile_database_operations: bool = True
    
    def validate(self) -> List[str]:
        """Validate configuration and return list of validation errors"""
        errors = []
        
        if self.episodes_limit and self.episodes_limit > self.safety.max_episodes_per_run:
            errors.append(f"episodes_limit ({self.episodes_limit}) exceeds safety limit ({self.safety.max_episodes_per_run})")
        
        if self.batch_size <= 0:
            errors.append("batch_size must be positive")
        
        if self.max_concurrent_episodes <= 0:
            errors.append("max_concurrent_episodes must be positive")
        
        if not self.output_dir:
            errors.append("output_dir must be specified")
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary for serialization"""
        return {
            'run_id': self.run_id,
            'description': self.description,
            'episodes_source': self.episodes_source,
            'episodes_limit': self.episodes_limit,
            'episodes_filter': self.episodes_filter,
            'batch_size': self.batch_size,
            'max_concurrent_episodes': self.max_concurrent_episodes,
            'enable_profiling': self.enable_profiling,
            'collect_memory_stats': self.collect_memory_stats,
            'hyperparameters': self.hyperparameters,
            'output_dir': str(self.output_dir),
            'export_formats': self.export_formats,
            'save_detailed_metrics': self.save_detailed_metrics,
            'profile_llm_calls': self.profile_llm_calls,
            'profile_embedding_calls': self.profile_embedding_calls,
            'profile_database_operations': self.profile_database_operations,
        }


@dataclass
class HyperparameterSpace:
    """Define hyperparameter search space for tuning"""
    
    # Entity extraction parameters
    entity_types: List[List[str]] = field(default_factory=list)
    max_entities_per_episode: List[int] = field(default_factory=lambda: [10, 20, 50])
    entity_similarity_threshold: List[float] = field(default_factory=lambda: [0.7, 0.8, 0.9])
    
    # LLM parameters
    temperature: List[float] = field(default_factory=lambda: [0.0, 0.3, 0.7])
    max_tokens: List[int] = field(default_factory=lambda: [1000, 2000, 4000])
    
    # Search parameters
    search_limit: List[int] = field(default_factory=lambda: [10, 20, 50])
    embedding_similarity_threshold: List[float] = field(default_factory=lambda: [0.6, 0.7, 0.8])
    
    # Deduplication parameters
    dedup_similarity_threshold: List[float] = field(default_factory=lambda: [0.85, 0.9, 0.95])
    
    def get_parameter_combinations(self) -> List[Dict[str, Any]]:
        """Generate all parameter combinations for grid search"""
        import itertools
        
        # Get all parameter fields and their values
        params = {}
        for field_name in self.__dataclass_fields__:
            values = getattr(self, field_name)
            if values:  # Only include non-empty lists
                params[field_name] = values
        
        if not params:
            return [{}]
        
        # Generate cartesian product of all parameter values
        keys = list(params.keys())
        values = list(params.values())
        
        combinations = []
        for combination in itertools.product(*values):
            param_dict = dict(zip(keys, combination))
            combinations.append(param_dict)
        
        return combinations