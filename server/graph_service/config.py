from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict  # type: ignore


class Settings(BaseSettings):
    openai_api_key: str
    openai_base_url: str | None = Field(None)
    model_name: str | None = Field(None)
    embedding_model_name: str | None = Field(None)
    
    # Database configuration - support both Neo4j and FalkorDB
    neo4j_uri: str | None = Field(None)
    neo4j_user: str | None = Field(None)
    neo4j_password: str | None = Field(None)
    
    falkordb_uri: str | None = Field(None)
    falkordb_host: str | None = Field(None)
    falkordb_port: int | None = Field(None)
    
    # Determine which database to use
    use_falkordb: bool = Field(False)
    
    # Cache invalidation configuration
    rust_server_url: str = Field("http://graph-visualizer-rust:3000")
    enable_cache_invalidation: bool = Field(True)
    cache_invalidation_timeout: int = Field(5000)  # milliseconds

    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    
    @property
    def database_uri(self) -> str:
        """Get the appropriate database URI based on configuration."""
        if self.use_falkordb or self.falkordb_uri or self.falkordb_host:
            if self.falkordb_uri:
                return self.falkordb_uri
            elif self.falkordb_host and self.falkordb_port:
                return f"redis://{self.falkordb_host}:{self.falkordb_port}"
            else:
                # Default to Docker service name and internal port
                return "redis://falkordb:6379"
        else:
            return self.neo4j_uri or "bolt://localhost:7687"
    
    @property
    def database_user(self) -> str:
        """Get the appropriate database user."""
        if self.use_falkordb or self.falkordb_uri or self.falkordb_host:
            return ""  # FalkorDB doesn't use authentication by default
        else:
            return self.neo4j_user or "neo4j"
    
    @property
    def database_password(self) -> str:
        """Get the appropriate database password."""
        if self.use_falkordb or self.falkordb_uri or self.falkordb_host:
            return ""  # FalkorDB doesn't use authentication by default
        else:
            return self.neo4j_password or "password"


@lru_cache
def get_settings():
    return Settings()  # type: ignore[call-arg]


ZepEnvDep = Annotated[Settings, Depends(get_settings)]
