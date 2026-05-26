import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

def extract_posted_date_from_job_id(job_id: str) -> str:
    if not job_id or len(job_id) < 6 or not job_id[:6].isdigit():
        return "N/A"

    try:
        posted_date = datetime.strptime(job_id[:6], "%d%m%y")
        return posted_date.strftime("%Y-%m-%d")
    except ValueError:
        return "N/A"

class JobDatabase:
    def __init__(self, db_path: str = None):
        self.db_path = db_path or settings.DATABASE_PATH
        self.init_database()
    
    def init_database(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    company TEXT NOT NULL,
                    location TEXT NOT NULL,
                    posted TEXT,
                    experience TEXT,
                    job_id TEXT UNIQUE NOT NULL,
                    link TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scrape_metadata (
                    id INTEGER PRIMARY KEY,
                    last_scraped_keywords TEXT,
                    last_scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_job_id ON jobs(job_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_company ON jobs(company)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_location ON jobs(location)")
            conn.commit()
    
    def save_jobs(self, jobs: List[Dict], keywords: List[str] = None) -> int:
        new_jobs = 0
        with sqlite3.connect(self.db_path) as conn:
            for job in jobs:
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO jobs 
                        (title, company, location, posted, experience, job_id, link)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        job.get('title', ''),
                        job.get('company', ''),
                        job.get('location', ''),
                        job.get('posted', ''),
                        job.get('experience', ''),
                        job.get('job_id', ''),
                        job.get('link', '')
                    ))
                    if conn.total_changes > 0:
                        new_jobs += 1
                except Exception as e:
                    logger.error(f"Error saving job {job.get('job_id', 'unknown')}: {e}")
            
            if keywords:
                keywords_str = ', '.join(keywords)
                conn.execute("""
                    INSERT OR REPLACE INTO scrape_metadata (id, last_scraped_keywords, last_scraped_at)
                    VALUES (1, ?, CURRENT_TIMESTAMP)
                """, (keywords_str,))
            
            conn.commit()
        logger.info(f"Saved {new_jobs} new jobs to database")
        return new_jobs
    
    def get_all_jobs(self) -> List[Dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT id, title, company, location, posted, experience, job_id, link
                FROM jobs
                ORDER BY
                    CASE WHEN posted IS NULL OR posted = 'N/A' THEN 1 ELSE 0 END,
                    date(posted) DESC,
                    created_at DESC
            """)
            return [self.normalize_job(row) for row in cursor.fetchall()]
    
    def get_jobs_filtered(self, search: str = None, location: str = None, 
                         min_experience: int = None, max_experience: int = None) -> List[Dict]:
        query = """
            SELECT id, title, company, location, posted, experience, job_id, link
            FROM jobs WHERE 1=1
        """
        params = []
        
        if search:
            query += " AND (title LIKE ? OR company LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        
        if location:
            query += " AND location LIKE ?"
            params.append(f"%{location}%")
        
        query += """
            ORDER BY
                CASE WHEN posted IS NULL OR posted = 'N/A' THEN 1 ELSE 0 END,
                date(posted) DESC,
                created_at DESC
        """
        
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            jobs = [self.normalize_job(row) for row in cursor.fetchall()]
            
            if min_experience is not None or max_experience is not None:
                filtered_jobs = []
                for job in jobs:
                    if not job['experience'] or job['experience'] == 'N/A':
                        continue
                    
                    import re
                    exp_match = re.match(r'(\d+)-to-(\d+)-years', job['experience'])
                    if not exp_match:
                        continue
                    
                    job_min_exp = int(exp_match.group(1))
                    job_max_exp = int(exp_match.group(2))
                    
                    filter_min = min_experience if min_experience is not None else 0
                    filter_max = max_experience if max_experience is not None else 50
                    
                    if job_max_exp >= filter_min and job_min_exp <= filter_max:
                        filtered_jobs.append(job)
                
                return filtered_jobs
            
            return jobs

    def normalize_job(self, row: sqlite3.Row) -> Dict:
        job = dict(row)
        if not job.get('posted') or job.get('posted') == 'N/A':
            job['posted'] = extract_posted_date_from_job_id(job.get('job_id'))

        return job
    
    def get_stats(self) -> Dict:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM jobs")
            total_jobs = cursor.fetchone()[0]
            
            cursor = conn.execute("SELECT DISTINCT location FROM jobs WHERE location != 'N/A'")
            locations = sorted([row[0] for row in cursor.fetchall()])
            
            cursor = conn.execute("SELECT DISTINCT company FROM jobs WHERE company != 'N/A'")
            companies = sorted([row[0] for row in cursor.fetchall()])
            
            cursor = conn.execute("SELECT DISTINCT experience FROM jobs WHERE experience != 'N/A' AND experience IS NOT NULL")
            experiences = sorted([row[0] for row in cursor.fetchall()])
            
            cursor = conn.execute("SELECT last_scraped_keywords FROM scrape_metadata WHERE id = 1")
            result = cursor.fetchone()
            last_keywords = result[0] if result else None
            
            return {
                'total_jobs': total_jobs,
                'unique_locations': len(locations),
                'unique_companies': len(companies),
                'unique_experiences': len(experiences),
                'locations': locations,
                'companies': companies,
                'experiences': experiences,
                'last_scraped_keywords': last_keywords
            }
    
    def clear_all_jobs(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM jobs")
            conn.commit()
        logger.info("Cleared all jobs from database")
