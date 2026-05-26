from pydantic import BaseModel
from typing import Optional, List

class JobBase(BaseModel):
    title: str
    company: str
    location: str
    posted: str
    experience: str
    job_id: str
    link: str

class Job(JobBase):
    id: int

class ScrapeRequest(BaseModel):
    keywords: List[str]
    latest_only: bool = True
    days: int = 7

class ScrapeResponse(BaseModel):
    success: bool
    count: int
    message: Optional[str] = None

class StatsResponse(BaseModel):
    total_jobs: int
    unique_locations: int
    unique_companies: int
    unique_experiences: int
    locations: List[str]
    companies: List[str]
    experiences: List[str]
    last_scraped_keywords: Optional[str] = None
