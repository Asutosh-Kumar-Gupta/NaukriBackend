from fastapi import APIRouter, HTTPException
from typing import List, Optional
import logging

from app.models.job import Job, ScrapeRequest, ScrapeResponse, StatsResponse
from app.services.database import JobDatabase
from app.services.scraper import scrape_jobs_with_keywords

logger = logging.getLogger(__name__)
router = APIRouter()
db = JobDatabase()

@router.get("/jobs", response_model=List[Job])
def get_jobs(
    search: Optional[str] = None,
    location: Optional[str] = None,
    min_experience: Optional[int] = None,
    max_experience: Optional[int] = None
):
    try:
        jobs = db.get_jobs_filtered(search, location, min_experience, max_experience)
        return jobs
    except Exception as e:
        logger.error(f"Error fetching jobs: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch jobs")

@router.post("/scrape", response_model=ScrapeResponse)
def trigger_scrape(request: ScrapeRequest):
    try:
        keywords = request.keywords if request.keywords else None
        logger.info(
            "Starting scraping process with keywords: %s, latest_only: %s, days: %s",
            keywords,
            request.latest_only,
            request.days
        )
        
        all_jobs = scrape_jobs_with_keywords(
            keywords,
            latest_only=request.latest_only,
            days=request.days
        )
        
        db.clear_all_jobs()
        new_jobs_count = db.save_jobs(all_jobs, keywords)
        message = f"Successfully scraped {len(all_jobs)} jobs ({new_jobs_count} new)"
        
        logger.info(f"Scraping completed: {message}")
        return ScrapeResponse(
            success=True, 
            count=new_jobs_count, 
            message=message
        )
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        raise HTTPException(status_code=500, detail=f"Scraping failed: {str(e)}")

@router.get("/stats", response_model=StatsResponse)
def get_stats():
    try:
        stats = db.get_stats()
        return StatsResponse(**stats)
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")

@router.delete("/jobs")
def clear_jobs():
    try:
        db.clear_all_jobs()
        return {"success": True, "message": "All jobs cleared from database"}
    except Exception as e:
        logger.error(f"Error clearing jobs: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear jobs")
