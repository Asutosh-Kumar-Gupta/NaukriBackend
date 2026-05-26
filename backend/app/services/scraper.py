import requests
import urllib3
import gzip
import xml.etree.ElementTree as ET
from io import BytesIO
import logging

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from datetime import datetime, timedelta
from typing import List, Dict, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://www.naukri.com/sitemap/incremental-jd-pages.xml"
KEYWORDS = ["python", "backend", "software engineer", "developer", "data scientist"]

def fetch_sitemap_urls() -> List[str]:
    try:
        logger.info(f"Fetching sitemap index from: {BASE_URL}")
        response = requests.get(BASE_URL, timeout=settings.REQUEST_TIMEOUT, verify=False)
        response.raise_for_status()
        logger.info(f"Sitemap index response status: {response.status_code}")
        
        root = ET.fromstring(response.content)
        ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        sitemap_urls = [s.find("ns:loc", ns).text for s in root.findall("ns:sitemap", ns)]
        
        logger.info(f"Found {len(sitemap_urls)} sitemap URLs")
        return sitemap_urls
    except Exception as e:
        logger.error(f"Error fetching sitemap URLs: {e}")
        return []

def fetch_job_urls(sitemap_url: str) -> List[str]:
    try:
        logger.debug(f"Fetching job URLs from: {sitemap_url}")
        response = requests.get(sitemap_url, timeout=settings.REQUEST_TIMEOUT, verify=False)
        response.raise_for_status()
        logger.debug(f"Sitemap response status: {response.status_code}")
        
        with gzip.GzipFile(fileobj=BytesIO(response.content)) as f:
            xml_data = f.read()
        root = ET.fromstring(xml_data)
        ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        job_urls = [u.find("ns:loc", ns).text for u in root.findall("ns:url", ns)]
        
        logger.debug(f"Extracted {len(job_urls)} job URLs from sitemap")
        return job_urls
    except Exception as e:
        logger.error(f"Error fetching job URLs from {sitemap_url}: {e}")
        return []

def filter_urls(urls: List[str], keywords: List[str] = None) -> List[str]:
    if not keywords:
        keywords = KEYWORDS
    
    filtered = [url for url in urls if any(k.lower() in url.lower() for k in keywords)]
    logger.info(f"Filtered {len(filtered)} URLs from {len(urls)} total URLs using keywords: {keywords}")
    return filtered

def extract_posted_date_from_job_id(job_id: str) -> str:
    if not job_id or len(job_id) < 6 or not job_id[:6].isdigit():
        return "N/A"

    try:
        posted_date = datetime.strptime(job_id[:6], "%d%m%y")
        return posted_date.strftime("%Y-%m-%d")
    except ValueError:
        logger.debug(f"Could not parse posted date from job ID: {job_id}")
        return "N/A"

def parse_posted_date(posted: str) -> Optional[datetime]:
    if not posted or posted == "N/A":
        return None

    try:
        return datetime.strptime(posted, "%Y-%m-%d")
    except ValueError:
        return None

def is_recent_job(job: Dict, days: int) -> bool:
    posted_date = parse_posted_date(job.get("posted", ""))
    if not posted_date:
        return False

    cutoff = datetime.now() - timedelta(days=max(days, 1))
    return posted_date >= cutoff

def scrape_job_details(job_url: str) -> Dict:
    try:
        logger.debug(f"Scraping job details from: {job_url}")
        
        # Parse URL pattern: job-listings-<role>-<company>-<city>-<experience>-<job_id>
        url_parts = job_url.split('/')[-1].replace('job-listings-', '').split('-')
        
        # Find "to" and "years" pattern for experience
        to_idx = -1
        years_idx = -1
        for i, part in enumerate(url_parts):
            if part == 'to':
                to_idx = i
            elif part == 'years':
                years_idx = i
                break
        
        if to_idx > 0 and years_idx > to_idx:
            # Extract parts before experience
            before_exp = url_parts[:to_idx-1]
            experience = f"{url_parts[to_idx-1]}-to-{url_parts[to_idx+1]}-years"
            job_id = url_parts[years_idx+1] if years_idx+1 < len(url_parts) else "N/A"
            
            # Split before_exp into role and company+location
            role_keywords = ['developer', 'engineer', 'lead', 'qa', 'automation', 'backend', 'frontend', 'fullstack']
            split_idx = len(before_exp) // 2  # default split
            
            # Find the last role keyword to get complete role
            for i in range(len(before_exp) - 1, -1, -1):
                if any(keyword in before_exp[i].lower() for keyword in role_keywords):
                    split_idx = i + 1
                    break
            
            role_parts = before_exp[:split_idx]
            remaining_parts = before_exp[split_idx:]
            
            # Last part is likely location, rest is company
            if remaining_parts:
                company_parts = remaining_parts[:-1] if len(remaining_parts) > 1 else remaining_parts
                location_parts = [remaining_parts[-1]] if len(remaining_parts) > 1 else []
            else:
                company_parts = []
                location_parts = []
        else:
            role_parts = url_parts[:2]
            company_parts = [url_parts[2]] if len(url_parts) > 2 else []
            location_parts = [url_parts[3]] if len(url_parts) > 3 else []
            experience = "N/A"
            job_id = url_parts[-1] if url_parts else "N/A"

        posted = extract_posted_date_from_job_id(job_id)
        
        return {
            'title': ' '.join(role_parts).replace('-', ' ').title() if role_parts else 'N/A',
            'company': ' '.join(company_parts).replace('-', ' ').title() if company_parts else 'N/A',
            'location': ' '.join(location_parts).replace('-', ' ').title() if location_parts else 'N/A',
            'posted': posted,
            'experience': experience,
            'job_id': job_id,
            'link': job_url
        }
    except Exception as e:
        logger.error(f"Error scraping job details from {job_url}: {e}")
        return None

def scrape_jobs_with_keywords(
    keywords: List[str] = None,
    latest_only: bool = False,
    days: int = 7
) -> List[Dict]:
    if not keywords:
        keywords = KEYWORDS
    
    logger.info(f"Starting job scraping with keywords: {keywords}")
    
    sitemap_urls = fetch_sitemap_urls()
    if not sitemap_urls:
        logger.warning("No sitemap URLs found")
        return []
    
    all_jobs = []
    job_count = 0
    
    for sitemap_url in sitemap_urls[:settings.MAX_SITEMAPS]:
        job_urls = fetch_job_urls(sitemap_url)
        filtered_urls = filter_urls(job_urls, keywords)
        
        for job_url in filtered_urls:
            job_details = scrape_job_details(job_url)
            if job_details and (not latest_only or is_recent_job(job_details, days)):
                all_jobs.append(job_details)
                job_count += 1

                if job_count >= settings.MAX_JOBS_PER_SESSION:
                    logger.info(f"Reached max jobs per session: {settings.MAX_JOBS_PER_SESSION}")
                    break

        if job_count >= settings.MAX_JOBS_PER_SESSION:
            break
    
    all_jobs.sort(
        key=lambda job: parse_posted_date(job.get("posted", "")) or datetime.min,
        reverse=True
    )
    logger.info(f"Scraped {len(all_jobs)} jobs successfully")
    return all_jobs
