"""
Supabase Database Manager for Job Scraper
Provides a unified interface for database operations using Supabase PostgreSQL.
"""

import os
import logging
from datetime import datetime
from typing import List, Dict, Optional
from supabase import create_client, Client
from config import Config

class SupabaseDatabaseManager:
    """Manages database operations using Supabase PostgreSQL."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # Get Supabase credentials from environment
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_ANON_KEY')
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_ANON_KEY must be set in environment variables")
        
        # Initialize Supabase client
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        self.logger.info("Supabase client initialized successfully")
    
    def create_tables_if_not_exist(self):
        """Create tables by testing operations and handling gracefully."""
        self.logger.info("Ensuring database tables exist...")
        
        tables_to_check = ['companies', 'jobs', 'scrapers', 'scraper_logs']
        
        for table_name in tables_to_check:
            try:
                # Try to select from table to see if it exists
                result = self.supabase.table(table_name).select('*').limit(1).execute()
                self.logger.info(f"✓ Table '{table_name}' exists and is accessible")
            except Exception as e:
                self.logger.warning(f"Table '{table_name}' may not exist: {e}")
                self.logger.info(f"Please ensure '{table_name}' table is created in Supabase dashboard")
        
        return True
    
    def init_database(self):
        """Initialize database tables automatically."""
        try:
            # First try the simple table check method
            self.create_tables_if_not_exist()
            
            # Show SQL commands for manual creation if needed
            sql_commands = [
                """
                CREATE TABLE IF NOT EXISTS companies (
                    id BIGSERIAL PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    job_board_url TEXT NOT NULL,
                    scraper_script TEXT,
                    last_scraped TIMESTAMP WITH TIME ZONE,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id BIGSERIAL PRIMARY KEY,
                    company_id BIGINT REFERENCES companies(id),
                    title TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    description TEXT,
                    requirements TEXT,
                    location TEXT,
                    posted_date DATE,
                    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS scrapers (
                    id BIGSERIAL PRIMARY KEY,
                    company_id BIGINT NOT NULL REFERENCES companies(id),
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
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    status TEXT DEFAULT 'active'
                );
                """,
                """
                CREATE TABLE IF NOT EXISTS scraper_logs (
                    id BIGSERIAL PRIMARY KEY,
                    company_id BIGINT REFERENCES companies(id),
                    scraper_id BIGINT REFERENCES scrapers(id),
                    execution_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    jobs_found INTEGER,
                    success BOOLEAN,
                    error_message TEXT
                );
                """
            ]
            
            self.logger.info("Creating database tables automatically...")
            
            # Execute each SQL command
            for i, sql in enumerate(sql_commands, 1):
                try:
                    self.logger.info(f"Executing SQL command {i}/4...")
                    # Use Supabase PostgREST to execute SQL
                    result = self.supabase.rpc('exec_sql', {'query': sql.strip()}).execute()
                    self.logger.info(f"✓ SQL command {i} executed successfully")
                except Exception as e:
                    # Try alternative method using raw SQL execution
                    try:
                        # For table creation, we can use the table() method with upsert
                        self.logger.info(f"Trying alternative method for command {i}...")
                        if "companies" in sql:
                            # Try to create a dummy record to ensure table exists
                            self.supabase.table('companies').select('id').limit(1).execute()
                        elif "jobs" in sql:
                            self.supabase.table('jobs').select('id').limit(1).execute()
                        elif "scrapers" in sql:
                            self.supabase.table('scrapers').select('id').limit(1).execute()
                        elif "scraper_logs" in sql:
                            self.supabase.table('scraper_logs').select('id').limit(1).execute()
                        self.logger.info(f"✓ Table for command {i} already exists or created")
                    except Exception as e2:
                        self.logger.warning(f"Could not execute SQL command {i}: {e2}")
                        self.logger.info("Tables may already exist or need to be created manually")
            
            self.logger.info("Database initialization completed!")
            return sql_commands
            
        except Exception as e:
            self.logger.error(f"Error preparing database initialization: {e}")
            raise
    
    def add_company(self, name: str, job_board_url: str, scraper_script: str = None) -> int:
        """Add a new company to track."""
        try:
            # Check if company already exists
            existing = self.get_company_by_name(name)
            if existing:
                self.logger.warning(f"Company {name} already exists with ID: {existing['id']}")
                return existing['id']
            
            data = {
                'name': name,
                'job_board_url': job_board_url,
                'scraper_script': scraper_script
            }
            
            result = self.supabase.table('companies').insert(data).execute()
            
            if result.data:
                company_id = result.data[0]['id']
                self.logger.info(f"Added company: {name} with ID: {company_id}")
                return company_id
            else:
                raise Exception("No data returned from insert")
                
        except Exception as e:
            self.logger.error(f"Error adding company {name}: {e}")
            raise
    
    def get_company_by_name(self, name: str) -> Optional[Dict]:
        """Get company information by name."""
        try:
            result = self.supabase.table('companies').select('*').eq('name', name).execute()
            
            if result.data:
                return result.data[0]
            return None
            
        except Exception as e:
            self.logger.error(f"Error getting company by name {name}: {e}")
            return None
    
    def get_all_active_companies(self) -> List[Dict]:
        """Get all active companies."""
        try:
            result = self.supabase.table('companies').select('*').eq('status', 'active').execute()
            return result.data or []
            
        except Exception as e:
            self.logger.error(f"Error getting active companies: {e}")
            return []
    
    def add_job(self, company_id: int, title: str, url: str, 
                description: str = None, requirements: str = None, 
                location: str = None, posted_date: str = None) -> bool:
        """Add a job posting (returns True if new job, False if duplicate)."""
        try:
            data = {
                'company_id': company_id,
                'title': title,
                'url': url,
                'description': description,
                'requirements': requirements,
                'location': location,
                'posted_date': posted_date
            }
            
            # Remove None values
            data = {k: v for k, v in data.items() if v is not None}
            
            result = self.supabase.table('jobs').insert(data).execute()
            
            if result.data:
                self.logger.info(f"Added new job: {title}")
                return True
            else:
                return False
                
        except Exception as e:
            # Check if it's a duplicate URL error
            if 'duplicate key' in str(e).lower() or 'unique constraint' in str(e).lower():
                self.logger.debug(f"Duplicate job URL: {url}")
                return False
            else:
                self.logger.error(f"Error adding job {title}: {e}")
                return False
    
    def add_jobs_batch(self, company_id: int, jobs: List[Dict]) -> Dict[str, int]:
        """Add multiple jobs in a batch with deduplication using single request."""
        results = {'added': 0, 'duplicates': 0, 'errors': 0}
        
        if not jobs:
            return results
        
        try:
            # Get existing URLs for duplicate detection
            existing_urls = self.get_existing_job_urls(company_id)
            
            # Prepare batch data
            batch_data = []
            for job in jobs:
                # Extract and validate job data
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
                
                # Skip duplicates
                if url in existing_urls:
                    results['duplicates'] += 1
                    continue
                
                # Prepare data for batch insert
                job_data = {
                    'company_id': company_id,
                    'title': title,
                    'url': url,
                    'description': description or None,
                    'requirements': requirements or None,
                    'location': location or None,
                    'posted_date': posted_date
                }
                
                # Remove None values
                job_data = {k: v for k, v in job_data.items() if v is not None}
                batch_data.append(job_data)
            
            # Perform batch insert if we have data
            if batch_data:
                result = self.supabase.table('jobs').insert(batch_data).execute()
                
                if result.data:
                    results['added'] = len(result.data)
                    self.logger.info(f"Successfully added {results['added']} jobs in batch")
                else:
                    results['errors'] = len(batch_data)
                    self.logger.error("Batch insert returned no data")
            
        except Exception as e:
            # If batch insert fails, log error but don't fall back to individual inserts
            results['errors'] = len(jobs)
            self.logger.error(f"Batch job insertion failed: {e}")
        
        self.logger.info(f"Batch job insertion complete: {results['added']} added, "
                        f"{results['duplicates']} duplicates, {results['errors']} errors")
        
        return results
    
    def get_jobs_by_company(self, company_id: int, limit: int = 100) -> List[Dict]:
        """Get jobs for a specific company."""
        try:
            result = self.supabase.table('jobs')\
                .select('*')\
                .eq('company_id', company_id)\
                .order('scraped_at', desc=True)\
                .limit(limit)\
                .execute()
            
            return result.data or []
            
        except Exception as e:
            self.logger.error(f"Error getting jobs by company {company_id}: {e}")
            return []
    
    def get_existing_job_urls(self, company_id: int) -> set:
        """Get all existing job URLs for a company to check for duplicates."""
        try:
            result = self.supabase.table('jobs')\
                .select('url')\
                .eq('company_id', company_id)\
                .execute()
            
            if result.data:
                return {job['url'] for job in result.data if job['url']}
            return set()
            
        except Exception as e:
            self.logger.error(f"Error getting existing job URLs for company {company_id}: {e}")
            return set()
    
    def log_scraper_execution(self, company_id: int, jobs_found: int, 
                            success: bool, error_message: str = None):
        """Log scraper execution results."""
        try:
            data = {
                'company_id': company_id,
                'jobs_found': jobs_found,
                'success': success,
                'error_message': error_message
            }
            
            self.supabase.table('scraper_logs').insert(data).execute()
            
        except Exception as e:
            self.logger.error(f"Error logging scraper execution: {e}")
    
    def get_scraper_stats(self, company_id: int, days: int = 7) -> Dict:
        """Get scraper statistics for a company."""
        try:
            # Get recent logs
            result = self.supabase.table('scraper_logs')\
                .select('*')\
                .eq('company_id', company_id)\
                .gte('execution_time', f'now() - interval \'{days} days\'')\
                .execute()
            
            logs = result.data or []
            
            if not logs:
                return {'total_runs': 0, 'successful_runs': 0, 'avg_jobs_found': 0, 'last_run': None}
            
            total_runs = len(logs)
            successful_runs = sum(1 for log in logs if log.get('success'))
            avg_jobs_found = sum(log.get('jobs_found', 0) for log in logs) / total_runs if total_runs > 0 else 0
            last_run = max(log['execution_time'] for log in logs) if logs else None
            
            return {
                'total_runs': total_runs,
                'successful_runs': successful_runs,
                'avg_jobs_found': avg_jobs_found,
                'last_run': last_run
            }
            
        except Exception as e:
            self.logger.error(f"Error getting scraper stats for company {company_id}: {e}")
            return {'total_runs': 0, 'successful_runs': 0, 'avg_jobs_found': 0, 'last_run': None}
    
    def get_recent_jobs(self, limit: int = 50) -> List[Dict]:
        """Get recent jobs with company information."""
        try:
            result = self.supabase.table('jobs')\
                .select('*, companies(name)')\
                .order('scraped_at', desc=True)\
                .limit(limit)\
                .execute()
            
            jobs = result.data or []
            
            # Flatten the company data
            for job in jobs:
                if job.get('companies'):
                    job['company_name'] = job['companies']['name']
                    del job['companies']
            
            return jobs
            
        except Exception as e:
            self.logger.error(f"Error getting recent jobs: {e}")
            return []
    
    def get_dashboard_stats(self) -> Dict:
        """Get statistics for the dashboard."""
        try:
            stats = {}
            
            # Total jobs
            result = self.supabase.table('jobs').select('id', count='exact').execute()
            stats['total_jobs'] = result.count or 0
            
            # Total companies
            result = self.supabase.table('companies')\
                .select('id', count='exact')\
                .eq('status', 'active')\
                .execute()
            stats['total_companies'] = result.count or 0
            
            # Jobs this week
            result = self.supabase.table('jobs')\
                .select('id', count='exact')\
                .gte('scraped_at', 'now() - interval \'7 days\'')\
                .execute()
            stats['jobs_this_week'] = result.count or 0
            
            # Jobs today
            result = self.supabase.table('jobs')\
                .select('id', count='exact')\
                .gte('scraped_at', 'now() - interval \'1 day\'')\
                .execute()
            stats['jobs_today'] = result.count or 0
            
            return stats
            
        except Exception as e:
            self.logger.error(f"Error getting dashboard stats: {e}")
            return {'total_jobs': 0, 'total_companies': 0, 'jobs_this_week': 0, 'jobs_today': 0}
    
    def search_jobs(self, search_query: str = None, company_filter: str = None, 
                   location_filter: str = None, limit: int = 50, offset: int = 0) -> Dict:
        """Search jobs with filters."""
        try:
            query = self.supabase.table('jobs').select('*, companies(name)')
            
            # Apply filters
            if company_filter:
                # First get company ID
                company = self.get_company_by_name(company_filter)
                if company:
                    query = query.eq('company_id', company['id'])
                else:
                    return {'jobs': [], 'total_count': 0}
            
            if search_query:
                # Note: Supabase doesn't have native full-text search on all plans
                # Using ilike for basic text search
                query = query.or_(f'title.ilike.%{search_query}%,description.ilike.%{search_query}%')
            
            if location_filter:
                query = query.ilike('location', f'%{location_filter}%')
            
            # Get total count for pagination
            count_result = query.select('id', count='exact').execute()
            total_count = count_result.count or 0
            
            # Get paginated results
            result = query.order('scraped_at', desc=True).range(offset, offset + limit - 1).execute()
            
            jobs = result.data or []
            
            # Flatten company data
            for job in jobs:
                if job.get('companies'):
                    job['company_name'] = job['companies']['name']
                    del job['companies']
            
            return {
                'jobs': jobs,
                'total_count': total_count
            }
            
        except Exception as e:
            self.logger.error(f"Error searching jobs: {e}")
            return {'jobs': [], 'total_count': 0}
    
    def get_companies_with_stats(self) -> List[Dict]:
        """Get companies with job statistics."""
        try:
            # Get companies with job counts
            result = self.supabase.table('companies')\
                .select('*, jobs(id)')\
                .eq('status', 'active')\
                .execute()
            
            companies = result.data or []
            
            # Calculate job counts and get last job date
            for company in companies:
                job_count = len(company.get('jobs', []))
                company['job_count'] = job_count
                
                # Get last job scraped
                if job_count > 0:
                    last_job_result = self.supabase.table('jobs')\
                        .select('scraped_at')\
                        .eq('company_id', company['id'])\
                        .order('scraped_at', desc=True)\
                        .limit(1)\
                        .execute()
                    
                    if last_job_result.data:
                        company['last_job_scraped'] = last_job_result.data[0]['scraped_at']
                    else:
                        company['last_job_scraped'] = None
                else:
                    company['last_job_scraped'] = None
                
                # Remove the jobs array (we only needed it for counting)
                del company['jobs']
            
            return companies
            
        except Exception as e:
            self.logger.error(f"Error getting companies with stats: {e}")
            return []
    
    def health_check(self) -> Dict:
        """Perform a health check on the database connection."""
        try:
            # Simple query to test connection
            result = self.supabase.table('companies').select('id').limit(1).execute()
            
            return {
                'status': 'healthy',
                'connected': True,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'unhealthy',
                'connected': False,
                'error': str(e),
                'timestamp': datetime.utcnow().isoformat()
            }