import sqlite3
import logging
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from config import Config

class DatabaseManager:
    """Manages SQLite database operations for the job scraper."""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or Config.DATABASE_PATH
        self.logger = logging.getLogger(__name__)
        self.init_database()
    
    def get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory and WAL mode."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        # Enable WAL mode for better concurrency and performance
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')  # Faster than FULL, still safe with WAL
        conn.execute('PRAGMA cache_size=10000')    # Increase cache size
        conn.execute('PRAGMA temp_store=memory')   # Store temp tables in memory
        
        return conn
    
    def init_database(self):
        """Initialize database with required tables."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Companies table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS companies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    job_board_url TEXT NOT NULL,
                    scraper_script TEXT,
                    last_scraped TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Jobs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    description TEXT,
                    requirements TEXT,
                    location TEXT,
                    posted_date DATE,
                    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (company_id) REFERENCES companies (id)
                )
            ''')
            
            # Scrapers table - stores scraper configurations
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scrapers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER NOT NULL,
                    job_container_selector TEXT NOT NULL,
                    title_selector TEXT NOT NULL,
                    url_selector TEXT NOT NULL,
                    description_selector TEXT,
                    location_selector TEXT,
                    requirements_selector TEXT,
                    pagination_selector TEXT,
                    has_dynamic_loading BOOLEAN DEFAULT FALSE,
                    max_pages INTEGER DEFAULT 3,
                    scrape_url TEXT NOT NULL,
                    confidence_score REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'active',
                    FOREIGN KEY (company_id) REFERENCES companies (id)
                )
            ''')
            
            # Scraper logs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scraper_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER,
                    scraper_id INTEGER,
                    execution_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    jobs_found INTEGER,
                    success BOOLEAN,
                    error_message TEXT,
                    FOREIGN KEY (company_id) REFERENCES companies (id),
                    FOREIGN KEY (scraper_id) REFERENCES scrapers (id)
                )
            ''')
            
            conn.commit()
            self.logger.info("Database initialized successfully")
    
    def add_company(self, name: str, job_board_url: str, scraper_script: str = None) -> int:
        """Add a new company to track."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO companies (name, job_board_url, scraper_script)
                    VALUES (?, ?, ?)
                ''', (name, job_board_url, scraper_script))
                conn.commit()
                company_id = cursor.lastrowid
                self.logger.info(f"Added company: {name} with ID: {company_id}")
                return company_id
            except sqlite3.IntegrityError:
                self.logger.warning(f"Company {name} already exists")
                return self.get_company_by_name(name)['id']
    
    def get_company_by_name(self, name: str) -> Optional[Dict]:
        """Get company information by name."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM companies WHERE name = ?', (name,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_all_active_companies(self) -> List[Dict]:
        """Get all active companies."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM companies WHERE status = "active"')
            return [dict(row) for row in cursor.fetchall()]
    
    def update_company_scraper(self, company_id: int, scraper_script: str):
        """Update the scraper script for a company."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE companies 
                SET scraper_script = ?, last_scraped = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (scraper_script, company_id))
            conn.commit()
    
    def get_company_scraper_config(self, company_id: int) -> Optional[Dict]:
        """Get stored scraper configuration for a company."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT scraper_script FROM companies WHERE id = ?', (company_id,))
            row = cursor.fetchone()
            if row and row['scraper_script']:
                try:
                    # Try to parse as JSON if it's a config, otherwise return as script
                    import json
                    return json.loads(row['scraper_script'])
                except (json.JSONDecodeError, TypeError):
                    # Return as script text if not JSON
                    return {'script': row['scraper_script']}
            return None
    
    def add_job(self, company_id: int, title: str, url: str, 
                description: str = None, requirements: str = None, 
                location: str = None, posted_date: str = None) -> bool:
        """Add a job posting (returns True if new job, False if duplicate)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO jobs (company_id, title, url, description, 
                                    requirements, location, posted_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (company_id, title, url, description, requirements, location, posted_date))
                conn.commit()
                self.logger.info(f"Added new job: {title}")
                return True
            except sqlite3.IntegrityError:
                self.logger.debug(f"Duplicate job URL: {url}")
                return False
    
    def add_jobs_batch(self, company_id: int, jobs: List[Dict]) -> Dict[str, int]:
        """
        Add multiple jobs in a batch with deduplication by URL.
        
        Args:
            company_id: ID of the company
            jobs: List of job dictionaries with keys: title, url, description, location, requirements
            
        Returns:
            Dictionary with counts: {'added': int, 'duplicates': int, 'errors': int}
        """
        results = {'added': 0, 'duplicates': 0, 'errors': 0}
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            for job in jobs:
                try:
                    # Extract job data
                    title = job.get('title', '').strip()
                    url = job.get('url', '').strip()
                    description = job.get('description', '').strip()
                    location = job.get('location', '').strip()
                    requirements = job.get('requirements', '').strip()
                    posted_date = job.get('posted_date')
                    
                    # Skip jobs without required fields
                    if not title or not url:
                        self.logger.warning(f"Skipping job with missing title or URL: {job}")
                        results['errors'] += 1
                        continue
                    
                    cursor.execute('''
                        INSERT INTO jobs (company_id, title, url, description, 
                                        requirements, location, posted_date)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (company_id, title, url, description, requirements, location, posted_date))
                    
                    results['added'] += 1
                    self.logger.debug(f"Added job: {title}")
                    
                except sqlite3.IntegrityError:
                    results['duplicates'] += 1
                    self.logger.debug(f"Duplicate job URL: {job.get('url', 'Unknown')}")
                    
                except Exception as e:
                    results['errors'] += 1
                    self.logger.error(f"Error adding job {job.get('title', 'Unknown')}: {str(e)}")
            
            conn.commit()
        
        self.logger.info(f"Batch job insertion complete: {results['added']} added, "
                        f"{results['duplicates']} duplicates, {results['errors']} errors")
        
        return results
    
    def get_jobs_by_company(self, company_id: int, limit: int = 100) -> List[Dict]:
        """Get jobs for a specific company."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM jobs 
                WHERE company_id = ? 
                ORDER BY scraped_at DESC 
                LIMIT ?
            ''', (company_id, limit))
            return [dict(row) for row in cursor.fetchall()]
    
    def log_scraper_execution(self, company_id: int, jobs_found: int, 
                            success: bool, error_message: str = None):
        """Log scraper execution results."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO scraper_logs (company_id, jobs_found, success, error_message)
                VALUES (?, ?, ?, ?)
            ''', (company_id, jobs_found, success, error_message))
            conn.commit()
    
    def get_scraper_stats(self, company_id: int, days: int = 7) -> Dict:
        """Get scraper statistics for a company."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    COUNT(*) as total_runs,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_runs,
                    AVG(jobs_found) as avg_jobs_found,
                    MAX(execution_time) as last_run
                FROM scraper_logs 
                WHERE company_id = ? 
                AND execution_time > datetime('now', '-' || ? || ' days')
            ''', (company_id, days))
            row = cursor.fetchone()
            return dict(row) if row else {}
    
    def cleanup_old_data(self, days: int = 30):
        """Clean up old scraper logs."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM scraper_logs 
                WHERE execution_time < datetime('now', '-' || ? || ' days')
            ''', (days,))
            deleted = cursor.rowcount
            conn.commit()
            self.logger.info(f"Cleaned up {deleted} old log entries")
            return deleted
    
    def checkpoint_wal(self):
        """Perform WAL checkpoint to merge WAL file back to main database."""
        try:
            with self.get_connection() as conn:
                conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
                conn.commit()
            self.logger.info("WAL checkpoint completed")
        except Exception as e:
            self.logger.warning(f"WAL checkpoint failed: {str(e)}")
    
    def get_database_info(self) -> Dict:
        """Get database file information including WAL files."""
        import os
        info = {
            'main_db': self.db_path,
            'main_db_exists': os.path.exists(self.db_path),
            'wal_file': f"{self.db_path}-wal",
            'wal_exists': os.path.exists(f"{self.db_path}-wal"),
            'shm_file': f"{self.db_path}-shm", 
            'shm_exists': os.path.exists(f"{self.db_path}-shm")
        }
        
        # Get file sizes
        for key in ['main_db', 'wal_file', 'shm_file']:
            file_path = info[key]
            if os.path.exists(file_path):
                info[f"{key}_size"] = os.path.getsize(file_path)
            else:
                info[f"{key}_size"] = 0
        
        return info
