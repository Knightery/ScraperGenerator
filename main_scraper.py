import os
import logging
from typing import Callable, Dict, List, Optional

from supabase_database import SupabaseDatabaseManager
from search_engine import SearchEngine
from ai_navigator import AINavigator
from config import Config
import subprocess
import sys
from dotenv import load_dotenv

load_dotenv()

class CompanyJobScraper:
    """Simplified main orchestrator for job scraping."""

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
        search_engine: Optional[SearchEngine] = None,
    ):
        self.setup_logging()
        self.db = SupabaseDatabaseManager()
        self.logger = logging.getLogger(__name__)

        self.gemini_api_key = gemini_api_key or os.getenv('GEMINI_API_KEY')
        self.progress_callback = progress_callback
        self.search_engine = search_engine or SearchEngine(gemini_api_key=self.gemini_api_key)
        
        self.logger.info("Job Scraper initialized")

    def _emit_progress(self, callback: Optional[Callable[[Dict], None]], payload: Dict):
        if not callback:
            return
        try:
            callback(payload)
        except Exception as exc:
            self.logger.debug(f"Progress callback failed: {exc}")
    
    def setup_logging(self):
        """Configure logging for the application."""
        logging.basicConfig(
            level=getattr(logging, Config.LOG_LEVEL),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('scraper.log'),
                logging.StreamHandler()
            ]
        )
    
    def add_company(
        self,
        company_name: str,
        gemini_api_key: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict], None]] = None,
    ) -> bool:
        """Add a company to the scraping system."""
        self.logger.info(f"Adding company: {company_name}")
        callback = progress_callback or self.progress_callback
        active_gemini_key = gemini_api_key or self.gemini_api_key
        local_search_engine = self.search_engine
        if gemini_api_key and gemini_api_key != self.gemini_api_key:
            local_search_engine = SearchEngine(gemini_api_key=gemini_api_key)
        elif local_search_engine is None:
            local_search_engine = SearchEngine(gemini_api_key=active_gemini_key)

        self._emit_progress(callback, {
            'stage': 'start',
            'message': f"Initializing scraper creation for {company_name}",
            'company': company_name,
        })
        
        try:
            # Search for job board
            self._emit_progress(callback, {'stage': 'search', 'message': 'Searching for job board URL', 'company': company_name})
            job_board_url = local_search_engine.search_company_jobs(company_name)
            if not job_board_url:
                self.logger.error(f"Could not find job board for {company_name}")
                self._emit_progress(callback, {
                    'stage': 'search',
                    'message': 'Unable to locate job board URL. Try refining the company name.',
                    'status': 'error',
                    'company': company_name,
                    'type': 'error'
                })
                return False
            self._emit_progress(callback, {
                'stage': 'search',
                'message': 'Job board discovered',
                'url': job_board_url,
                'company': company_name
            })
            
            # Create AI navigator with search engine context for this company
            if not active_gemini_key:
                raise ValueError("GEMINI_API_KEY must be provided to create a scraper")

            ai_navigator = AINavigator(
                search_engine=local_search_engine,
                company_name=company_name,
                gemini_api_key=active_gemini_key,
                progress_callback=lambda payload: self._emit_progress(
                    callback,
                    {**payload, 'company': company_name}
                )
            )
            self._emit_progress(callback, {'stage': 'analysis', 'message': 'Analyzing job board structure', 'company': company_name})
            
            # AI analyzes and validates the site
            analysis = ai_navigator.analyze_job_board(job_board_url)
            if "error" in analysis:
                self.logger.error(f"Site analysis failed: {analysis['error']}")
                self._emit_progress(callback, {
                    'stage': 'analysis',
                    'message': analysis['error'],
                    'status': 'error',
                    'company': company_name,
                    'type': 'error'
                })
                return False
            
            # Generate scraper script
            scraper_script = ai_navigator.generate_scraper_script(
                company_name, job_board_url, analysis
            )
            self._emit_progress(callback, {'stage': 'generation', 'message': 'Scraper script generated', 'company': company_name})
            
            # Check if this is monitor mode (no internships found)
            monitor_mode = analysis.get('monitor_mode', False) or analysis.get('no_internships_found', False)
            
            # Store in database
            final_url = analysis.get("final_url", job_board_url)
            company_id = self.db.add_company_with_mode(company_name, final_url, scraper_script, monitor_mode=monitor_mode)
            
            mode_str = "MONITOR MODE" if monitor_mode else "NORMAL MODE"
            self._emit_progress(callback, {
                'stage': 'storage',
                'message': f'Company persisted to Supabase ({mode_str})',
                'company_id': company_id,
                'company': company_name,
                'monitor_mode': monitor_mode
            })
            
            # Create scrapers directory if it doesn't exist
            scrapers_dir = "scrapers"
            os.makedirs(scrapers_dir, exist_ok=True)
            
            # Save standalone scraper script (monitor or normal)
            if monitor_mode:
                script_file = os.path.join(scrapers_dir, f"{company_name.lower().replace(' ', '_')}_monitor.py")
                success_message = f'Monitor scraper ready for {company_name} (will check for new internships)'
            else:
                script_file = os.path.join(scrapers_dir, f"{company_name.lower().replace(' ', '_')}_scraper.py")
                success_message = f'Scraper ready for {company_name}'
            
            with open(script_file, 'w') as f:
                f.write(scraper_script)
            
            self.logger.info(f"Successfully added {company_name} (ID: {company_id}) - {mode_str}")
            self._emit_progress(callback, {
                'stage': 'complete',
                'status': 'success',
                'message': success_message,
                'script_file': script_file,
                'config_url': final_url,
                'company': company_name,
                'monitor_mode': monitor_mode,
                'type': 'complete'
            })
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add company {company_name}: {str(e)}")
            self._emit_progress(callback, {
                'stage': 'error',
                'status': 'error',
                'message': str(e),
                'company': company_name,
                'type': 'error'
            })
            return False
    
    
    def scrape_company(self, company_name: str) -> List[Dict]:
        """Scrape jobs for a specific company using database-integrated scraper."""
        company = self.db.get_company_by_name(company_name)
        if not company:
            self.logger.error(f"Company {company_name} not found in database")
            return []
        
        try:
            # Check if this is a monitor-mode company
            monitor_mode = company.get('monitor_mode', False)
            
            if monitor_mode:
                # Execute monitor scraper (checks for changes, not jobs)
                script_file = os.path.join("scrapers", f"{company_name.lower().replace(' ', '_')}_monitor.py")
            else:
                # Execute regular scraper
                script_file = os.path.join("scrapers", f"{company_name.lower().replace(' ', '_')}_scraper.py")
            
            if not os.path.exists(script_file):
                self.logger.error(f"Scraper script not found: {script_file}")
                return []
                
            result = subprocess.run([sys.executable, script_file], 
                                    capture_output=True, text=True, cwd=os.getcwd())
            
            if result.returncode == 0:
                self.logger.info(f"Successfully executed scraper for {company_name}")
                
                if monitor_mode:
                    # Monitor mode - no jobs expected, just checking for changes
                    self.logger.info(f"Monitor mode: Check complete. See output for change detection results.")
                    # Print the monitor output for user visibility
                    print(result.stdout)
                    return []
                else:
                    # Normal mode - get recently scraped jobs from database
                    recent_jobs = self.db.get_jobs_by_company(company['id'], limit=50)
                    return recent_jobs
            else:
                self.logger.error(f"Scraper failed for {company_name}: {result.stderr}")
                # Log the failure
                self.db.log_scraper_execution(company['id'], 0, False, result.stderr)
                return []
            
        except Exception as e:
            self.logger.error(f"Error running scraper for {company_name}: {str(e)}")
            # Log the failure
            self.db.log_scraper_execution(company['id'], 0, False, str(e))
            return []
    
    def get_company_stats(self, company_name: str) -> Dict:
        """Get statistics for a company."""
        company = self.db.get_company_by_name(company_name)
        if not company:
            return {"error": "Company not found"}
        
        stats = self.db.get_scraper_stats(company['id'])
        jobs = self.db.get_jobs_by_company(company['id'], limit=10)
        
        return {
            "company": company,
            "stats": stats,
            "recent_jobs": jobs
        }
