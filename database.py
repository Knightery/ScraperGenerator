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
        """Get a database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
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
            
            # Scraper logs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scraper_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id INTEGER,
                    execution_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    jobs_found INTEGER,
                    success BOOLEAN,
                    error_message TEXT,
                    FOREIGN KEY (company_id) REFERENCES companies (id)
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
