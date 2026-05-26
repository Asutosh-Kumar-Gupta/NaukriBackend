from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    PROJECT_NAME: str = "Job Scraper API"
    VERSION: str = "1.0.0"
    DATABASE_PATH: str = "jobs.db"
    ALLOWED_HOSTS: List[str] = ["*"]
    LOG_LEVEL: str = "INFO"
    
    # Scraping settings
    MAX_SITEMAPS: int = 20
    MAX_JOBS_PER_SESSION: int = 2000
    REQUEST_TIMEOUT: int = 10
    
    class Config:
        env_file = ".env"

settings = Settings()