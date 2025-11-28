"""Application configuration."""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""
    
    # Gemini API
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    
    # Home Assistant
    supervisor_token: str = ""
    ha_base_url: str = "http://supervisor/core"
    
    # Ingress
    ingress_path: str = ""
    
    # Data
    data_dir: str = "/data"
    
    # Debug
    debug: bool = False
    
    @property
    def is_ha_addon(self) -> bool:
        """Check if running as HA add-on."""
        return bool(self.supervisor_token)
    
    @property
    def db_path(self) -> str:
        """Path to SQLite database."""
        return os.path.join(self.data_dir, "twinsync.db")
    
    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
