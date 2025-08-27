"""
Configuration management for sync service.

This module provides centralized configuration management with support for
environment variables, configuration files, and validation.
"""

import os
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, validator


logger = logging.getLogger(__name__)


class Neo4jConfig(BaseModel):
    """Neo4j database configuration."""
    uri: str = Field(default="bolt://neo4j:7687", description="Neo4j connection URI")
    user: str = Field(default="neo4j", description="Neo4j username")  
    password: str = Field(default="password", description="Neo4j password")
    database: str = Field(default="neo4j", description="Neo4j database name")
    pool_size: int = Field(default=10, description="Connection pool size", ge=1, le=100)
    
    @validator('uri')
    def validate_uri(cls, v):
        """Validate Neo4j URI format."""
        if not v.startswith(('bolt://', 'neo4j://', 'bolt+s://', 'neo4j+s://')):
            raise ValueError('Neo4j URI must start with bolt:// or neo4j://')
        return v


class FalkorDBConfig(BaseModel):
    """FalkorDB database configuration."""
    host: str = Field(default="falkordb", description="FalkorDB host")
    port: int = Field(default=6379, description="FalkorDB port", ge=1, le=65535)
    username: Optional[str] = Field(default=None, description="FalkorDB username")
    password: Optional[str] = Field(default=None, description="FalkorDB password")
    database: str = Field(default="graphiti_cache", description="FalkorDB graph name")
    
    @validator('host')
    def validate_host(cls, v):
        """Validate hostname format."""
        if not v or v.isspace():
            raise ValueError('Host cannot be empty')
        return v.strip()


class SyncConfig(BaseModel):
    """Sync operation configuration."""
    interval_seconds: int = Field(default=300, description="Sync interval in seconds", ge=10)
    batch_size: int = Field(default=1000, description="Batch size for processing", ge=100, le=10000)
    full_sync_on_startup: bool = Field(default=False, description="Perform full sync on startup")
    enable_incremental: bool = Field(default=True, description="Enable incremental sync")
    enable_continuous: bool = Field(default=True, description="Enable continuous sync")
    sync_direction: str = Field(default="forward", description="Sync direction: forward (Neo4j→FalkorDB) or reverse (FalkorDB→Neo4j)")
    enable_reverse_incremental: bool = Field(default=False, description="Enable reverse incremental sync")
    auto_recovery: bool = Field(default=True, description="Enable automatic disaster recovery (Neo4j→FalkorDB when FalkorDB is empty)")
    max_retries: int = Field(default=3, description="Maximum retry attempts", ge=1, le=10)
    retry_delay_seconds: int = Field(default=30, description="Delay between retries", ge=1)
    
    @validator('interval_seconds')
    def validate_interval(cls, v):
        """Validate sync interval is reasonable."""
        if v < 10:
            raise ValueError('Sync interval must be at least 10 seconds')
        if v > 86400:  # 24 hours
            raise ValueError('Sync interval cannot exceed 24 hours')
        return v
    
    @validator('sync_direction')
    def validate_sync_direction(cls, v):
        """Validate sync direction."""
        valid_directions = ['forward', 'reverse']
        if v.lower() not in valid_directions:
            raise ValueError(f'Sync direction must be one of: {valid_directions}')
        return v.lower()


class MigrationConfig(BaseModel):
    """Migration service configuration."""
    enabled: bool = Field(default=True, description="Enable migration service")
    max_query_length: int = Field(default=10000, description="Maximum Cypher query length", ge=1000, le=50000)
    skip_large_arrays: bool = Field(default=True, description="Skip properties with large arrays")
    max_array_size: int = Field(default=100, description="Maximum array size to include", ge=10, le=1000)
    retry_attempts: int = Field(default=3, description="Number of retry attempts for failed operations", ge=1, le=10)
    batch_progress_interval: int = Field(default=50, description="Progress reporting interval", ge=1, le=1000)
    clear_target_on_start: bool = Field(default=True, description="Clear target database before migration")
    use_for_disaster_recovery: bool = Field(default=True, description="Use migration service for disaster recovery")
    embedding_properties: List[str] = Field(
        default=['name_embedding', 'summary_embedding', 'embedding', 'embeddings'],
        description="Property names to skip (typically large embedding arrays)"
    )
    
    @validator('max_query_length')
    def validate_query_length(cls, v):
        """Validate query length is reasonable."""
        if v < 1000:
            raise ValueError('Max query length must be at least 1000 characters')
        if v > 50000:
            raise ValueError('Max query length cannot exceed 50000 characters')
        return v


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="json", description="Log format (text or json)")
    file_path: Optional[str] = Field(default=None, description="Log file path")
    max_file_size_mb: int = Field(default=100, description="Max log file size in MB", ge=1)
    backup_count: int = Field(default=5, description="Number of backup log files", ge=1)
    
    @validator('level')
    def validate_level(cls, v):
        """Validate log level."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of: {valid_levels}')
        return v.upper()
        
    @validator('format')
    def validate_format(cls, v):
        """Validate log format."""
        valid_formats = ['text', 'json']
        if v.lower() not in valid_formats:
            raise ValueError(f'Log format must be one of: {valid_formats}')
        return v.lower()


class MonitoringConfig(BaseModel):
    """Monitoring and health check configuration."""
    health_port: int = Field(default=8080, description="Health check port", ge=1024, le=65535)
    health_path: str = Field(default="/health", description="Health check endpoint path")
    metrics_enabled: bool = Field(default=True, description="Enable metrics collection")
    metrics_port: int = Field(default=8081, description="Metrics port", ge=1024, le=65535)
    metrics_path: str = Field(default="/metrics", description="Metrics endpoint path")
    
    @validator('health_path', 'metrics_path')
    def validate_paths(cls, v):
        """Validate endpoint paths."""
        if not v.startswith('/'):
            v = '/' + v
        return v


class SyncServiceConfig(BaseModel):
    """Complete sync service configuration."""
    neo4j: Neo4jConfig = Field(default_factory=Neo4jConfig)
    falkordb: FalkorDBConfig = Field(default_factory=FalkorDBConfig)
    sync: SyncConfig = Field(default_factory=SyncConfig)
    migration: MigrationConfig = Field(default_factory=MigrationConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    
    class Config:
        """Pydantic configuration."""
        env_prefix = "SYNC_"
        env_nested_delimiter = "__"
        case_sensitive = False


def load_config_from_env() -> SyncServiceConfig:
    """
    Load configuration from environment variables.
    
    Returns:
        SyncServiceConfig instance populated from environment
    """
    # Map environment variables to config structure
    env_mapping = {
        # Neo4j config
        'NEO4J_URI': 'neo4j.uri',
        'NEO4J_USER': 'neo4j.user', 
        'NEO4J_PASSWORD': 'neo4j.password',
        'NEO4J_DATABASE': 'neo4j.database',
        'NEO4J_POOL_SIZE': 'neo4j.pool_size',
        
        # FalkorDB config
        'FALKORDB_HOST': 'falkordb.host',
        'FALKORDB_PORT': 'falkordb.port',
        'FALKORDB_USERNAME': 'falkordb.username',
        'FALKORDB_PASSWORD': 'falkordb.password', 
        'FALKORDB_DATABASE': 'falkordb.database',
        'FALKORDB_POOL_SIZE': 'falkordb.pool_size',
        
        # Sync config
        'SYNC_INTERVAL_SECONDS': 'sync.interval_seconds',
        'SYNC_BATCH_SIZE': 'sync.batch_size',
        'SYNC_FULL_ON_STARTUP': 'sync.full_sync_on_startup',
        'SYNC_ENABLE_INCREMENTAL': 'sync.enable_incremental',
        'SYNC_ENABLE_CONTINUOUS': 'sync.enable_continuous',
        'SYNC_DIRECTION': 'sync.sync_direction',
        'SYNC_ENABLE_REVERSE_INCREMENTAL': 'sync.enable_reverse_incremental',
        'SYNC_AUTO_RECOVERY': 'sync.auto_recovery',
        'SYNC_MAX_RETRIES': 'sync.max_retries',
        'SYNC_RETRY_DELAY': 'sync.retry_delay_seconds',
        
        # Logging config
        'LOG_LEVEL': 'logging.level',
        'LOG_FORMAT': 'logging.format',
        'LOG_FILE_PATH': 'logging.file_path',
        'LOG_MAX_FILE_SIZE_MB': 'logging.max_file_size_mb',
        'LOG_BACKUP_COUNT': 'logging.backup_count',
        
        # Monitoring config
        'HEALTH_PORT': 'monitoring.health_port',
        'HEALTH_PATH': 'monitoring.health_path',
        'METRICS_ENABLED': 'monitoring.metrics_enabled',
        'METRICS_PORT': 'monitoring.metrics_port', 
        'METRICS_PATH': 'monitoring.metrics_path',
    }
    
    # Create config dict from environment
    config_dict = {}
    
    for env_var, config_path in env_mapping.items():
        value = os.getenv(env_var)
        if value is not None:
            # Navigate to nested dict position
            keys = config_path.split('.')
            current = config_dict
            
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]
                
            # Set final value with type conversion
            final_key = keys[-1]
            
            # Convert boolean values
            if value.lower() in ('true', 'false'):
                current[final_key] = value.lower() == 'true'
            # Convert numeric values
            elif value.isdigit():
                current[final_key] = int(value)
            else:
                current[final_key] = value
                
    return SyncServiceConfig(**config_dict)


def load_config_from_file(file_path: str) -> SyncServiceConfig:
    """
    Load configuration from YAML file.
    
    Args:
        file_path: Path to configuration file
        
    Returns:
        SyncServiceConfig instance
    """
    config_path = Path(file_path)
    
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
        
    with open(config_path, 'r') as f:
        config_dict = yaml.safe_load(f)
        
    return SyncServiceConfig(**config_dict)


def load_config(config_file: Optional[str] = None) -> SyncServiceConfig:
    """
    Load configuration with priority: file > environment > defaults.
    
    Args:
        config_file: Optional path to configuration file
        
    Returns:
        SyncServiceConfig instance
    """
    # Start with environment variables
    config = load_config_from_env()
    
    # Override with file if provided
    if config_file and os.path.exists(config_file):
        try:
            file_config = load_config_from_file(config_file)
            # Merge configurations (file takes precedence)
            config = merge_configs(config, file_config)
            logger.info(f"Loaded configuration from file: {config_file}")
        except Exception as e:
            logger.error(f"Failed to load config file {config_file}: {e}")
            logger.info("Using environment/default configuration")
    
    return config


def merge_configs(base: SyncServiceConfig, override: SyncServiceConfig) -> SyncServiceConfig:
    """
    Merge two configurations with override taking precedence.
    
    Args:
        base: Base configuration
        override: Override configuration
        
    Returns:
        Merged SyncServiceConfig
    """
    # Convert to dicts
    base_dict = base.dict()
    override_dict = override.dict()
    
    # Merge dictionaries recursively
    merged_dict = _merge_dicts(base_dict, override_dict)
    
    return SyncServiceConfig(**merged_dict)


def _merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge two dictionaries."""
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value
            
    return result


def save_config_to_file(config: SyncServiceConfig, file_path: str) -> None:
    """
    Save configuration to YAML file.
    
    Args:
        config: Configuration to save
        file_path: Target file path
    """
    config_dict = config.dict()
    
    with open(file_path, 'w') as f:
        yaml.dump(config_dict, f, default_flow_style=False, indent=2)
        
    logger.info(f"Configuration saved to: {file_path}")


def validate_config(config: SyncServiceConfig) -> None:
    """
    Validate configuration and log any issues.
    
    Args:
        config: Configuration to validate
    """
    # Additional validation beyond Pydantic
    
    # Check port conflicts
    ports_used = set()
    
    if config.monitoring.health_port in ports_used:
        raise ValueError("Port conflict: health_port already in use")
    ports_used.add(config.monitoring.health_port)
    
    if config.monitoring.metrics_enabled:
        if config.monitoring.metrics_port in ports_used:
            raise ValueError("Port conflict: metrics_port already in use")
        ports_used.add(config.monitoring.metrics_port)
        
    # Validate database connectivity would require actual connections
    # This is done at runtime during service startup
    
    logger.info("Configuration validation passed")