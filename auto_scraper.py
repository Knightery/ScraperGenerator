#!/usr/bin/env python3
"""
Auto-scraper service that runs all company scrapers every hour.
Perfect for running in a screen session on a VPS.

Usage:
    python auto_scraper.py                    # Run continuously
    python auto_scraper.py --once             # Run once and exit
    python auto_scraper.py --interval 30      # Custom interval in minutes
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import List, Dict

from supabase_database import SupabaseDatabaseManager

class AutoScraper:
    """Automated scraper service that runs all company scrapers on schedule."""
    
    def __init__(self, interval_minutes: int = 60):
        self.interval_minutes = interval_minutes
        self.db = SupabaseDatabaseManager()
        self.setup_logging()
        self.logger = logging.getLogger(__name__)
        self.scrapers_dir = "scrapers"
        self.logs_dir = "logs"
        
        # Create necessary directories
        os.makedirs(self.scrapers_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)
        
        self.logger.info(f"Auto-scraper initialized with {interval_minutes}-minute intervals")
    
    def setup_logging(self):
        """Setup logging for the auto-scraper."""
        os.makedirs("logs", exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('logs/auto_scraper.log'),
                logging.StreamHandler()
            ]
        )
    
    def get_active_companies(self) -> List[Dict]:
        """Get all active companies that have scraper scripts."""
        companies = self.db.get_all_active_companies()
        companies_with_scrapers = []
        
        for company in companies:
            script_file = os.path.join(self.scrapers_dir, f"{company['name'].lower().replace(' ', '_')}_scraper.py")
            if os.path.exists(script_file):
                companies_with_scrapers.append({
                    **company,
                    'script_file': script_file
                })
            else:
                self.logger.warning(f"No scraper script found for {company['name']} at {script_file}")
        
        return companies_with_scrapers
    
    def run_scraper(self, company: Dict) -> Dict:
        """Run a single company's scraper and return results."""
        company_name = company['name']
        script_file = company['script_file']
        
        self.logger.info(f"Starting scraper for {company_name}")
        
        start_time = datetime.now()
        
        try:
            # Run the scraper script
            result = subprocess.run(
                [sys.executable, script_file],
                capture_output=True,
                text=True,
                timeout=1800,  # 30-minute timeout per scraper
                cwd=os.getcwd()
            )
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            if result.returncode == 0:
                # Parse output to get job count
                output_lines = result.stdout.split('\n')
                jobs_found = 0
                
                for line in output_lines:
                    if 'Jobs found:' in line:
                        try:
                            jobs_found = int(line.split('Jobs found:')[1].strip())
                        except:
                            pass
                
                self.logger.info(f"✓ {company_name}: {jobs_found} jobs scraped in {duration:.1f}s")
                
                # Log successful execution
                self.db.log_scraper_execution(
                    company['id'], 
                    jobs_found, 
                    success=True
                )
                
                return {
                    'company': company_name,
                    'success': True,
                    'jobs_found': jobs_found,
                    'duration': duration,
                    'message': f"Successfully scraped {jobs_found} jobs"
                }
                
            else:
                error_msg = result.stderr or "Unknown error"
                self.logger.error(f"✗ {company_name}: Scraper failed - {error_msg}")
                
                # Log failed execution
                self.db.log_scraper_execution(
                    company['id'], 
                    0, 
                    success=False,
                    error_message=error_msg
                )
                
                return {
                    'company': company_name,
                    'success': False,
                    'jobs_found': 0,
                    'duration': duration,
                    'error': error_msg
                }
                
        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            error_msg = f"Scraper timed out after {duration:.1f} seconds"
            self.logger.error(f"✗ {company_name}: {error_msg}")
            
            # Log timeout as failure
            self.db.log_scraper_execution(
                company['id'], 
                0, 
                success=False,
                error_message=error_msg
            )
            
            return {
                'company': company_name,
                'success': False,
                'jobs_found': 0,
                'duration': duration,
                'error': error_msg
            }
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            error_msg = f"Unexpected error: {str(e)}"
            self.logger.error(f"✗ {company_name}: {error_msg}")
            
            # Log unexpected error
            self.db.log_scraper_execution(
                company['id'], 
                0, 
                success=False,
                error_message=error_msg
            )
            
            return {
                'company': company_name,
                'success': False,
                'jobs_found': 0,
                'duration': duration,
                'error': error_msg
            }
    
    def run_all_scrapers(self) -> Dict:
        """Run all company scrapers and return summary."""
        companies = self.get_active_companies()
        
        if not companies:
            self.logger.warning("No companies with scraper scripts found")
            return {
                'total_companies': 0,
                'successful': 0,
                'failed': 0,
                'total_jobs': 0,
                'duration': 0,
                'results': []
            }
        
        self.logger.info(f"Starting scraping run for {len(companies)} companies")
        
        start_time = datetime.now()
        results = []
        successful = 0
        failed = 0
        total_jobs = 0
        
        for i, company in enumerate(companies, 1):
            self.logger.info(f"[{i}/{len(companies)}] Processing {company['name']}")
            
            result = self.run_scraper(company)
            results.append(result)
            
            if result['success']:
                successful += 1
                total_jobs += result['jobs_found']
            else:
                failed += 1
            
            # Add a small delay between scrapers to be respectful
            if i < len(companies):
                time.sleep(10)
        
        end_time = datetime.now()
        total_duration = (end_time - start_time).total_seconds()
        
        summary = {
            'total_companies': len(companies),
            'successful': successful,
            'failed': failed,
            'total_jobs': total_jobs,
            'duration': total_duration,
            'results': results,
            'timestamp': start_time.isoformat()
        }
        
        self.logger.info(f"Scraping run complete: {successful}/{len(companies)} successful, "
                        f"{total_jobs} total jobs in {total_duration:.1f}s")
        
        return summary
    
    def print_status_report(self, summary: Dict):
        """Print a formatted status report."""
        print("\n" + "="*60)
        print(f"AUTO-SCRAPER STATUS REPORT")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        print(f"Companies Processed: {summary['total_companies']}")
        print(f"Successful: {summary['successful']}")
        print(f"Failed: {summary['failed']}")
        print(f"Total Jobs Found: {summary['total_jobs']}")
        print(f"Total Duration: {summary['duration']:.1f} seconds")
        print("-"*60)
        
        # Show individual results
        for result in summary['results']:
            status = "✓" if result['success'] else "✗"
            if result['success']:
                print(f"{status} {result['company']}: {result['jobs_found']} jobs ({result['duration']:.1f}s)")
            else:
                error = result.get('error', 'Unknown error')[:50]
                print(f"{status} {result['company']}: FAILED - {error}")
        
        print("="*60)
    
    def run_once(self):
        """Run all scrapers once and exit."""
        self.logger.info("Running auto-scraper once")
        summary = self.run_all_scrapers()
        self.print_status_report(summary)
        return summary
    
    def run_continuously(self):
        """Run scrapers continuously at specified intervals."""
        self.logger.info(f"Starting continuous auto-scraper (every {self.interval_minutes} minutes)")
        print(f"Auto-scraper started! Running every {self.interval_minutes} minutes.")
        print("Press Ctrl+C to stop.")
        
        try:
            while True:
                next_run = datetime.now() + timedelta(minutes=self.interval_minutes)
                
                # Run all scrapers
                summary = self.run_all_scrapers()
                self.print_status_report(summary)
                
                # Calculate sleep time
                now = datetime.now()
                if now < next_run:
                    sleep_seconds = (next_run - now).total_seconds()
                    self.logger.info(f"Next run scheduled at {next_run.strftime('%H:%M:%S')} "
                                   f"(sleeping {sleep_seconds/60:.1f} minutes)")
                    
                    # Sleep in chunks to allow for graceful shutdown
                    while sleep_seconds > 0 and datetime.now() < next_run:
                        chunk_sleep = min(60, sleep_seconds)  # Sleep in 1-minute chunks
                        time.sleep(chunk_sleep)
                        sleep_seconds -= chunk_sleep
                
        except KeyboardInterrupt:
            self.logger.info("Auto-scraper stopped by user")
            print("\nAuto-scraper stopped.")
    
    def get_status(self) -> Dict:
        """Get current status of the auto-scraper system."""
        companies = self.get_active_companies()
        
        stats = self.db.get_scraper_activity_summary(hours=24)

        return {
            'active_companies': len(companies),
            'companies': [c['name'] for c in companies],
            'interval_minutes': self.interval_minutes,
            'last_24h_stats': stats,
            'status': 'running' if companies else 'no_companies'
        }


def main():
    """Main function for auto-scraper CLI."""
    parser = argparse.ArgumentParser(
        description="Auto-scraper service for job scrapers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python auto_scraper.py                    # Run continuously every hour
  python auto_scraper.py --once             # Run once and exit
  python auto_scraper.py --interval 30      # Run every 30 minutes
  python auto_scraper.py --status           # Show current status
  
For VPS deployment:
  screen -S auto_scraper
  python auto_scraper.py --interval 60
  # Press Ctrl+A then D to detach from screen
        """
    )
    
    parser.add_argument('--once', action='store_true',
                       help='Run once and exit (don\'t run continuously)')
    parser.add_argument('--interval', type=int, default=60,
                       help='Interval between runs in minutes (default: 60)')
    parser.add_argument('--status', action='store_true',
                       help='Show current status and exit')
    
    args = parser.parse_args()
    
    try:
        auto_scraper = AutoScraper(interval_minutes=args.interval)
        
        if args.status:
            status = auto_scraper.get_status()
            print("\n=== AUTO-SCRAPER STATUS ===")
            print(f"Active Companies: {status['active_companies']}")
            print(f"Companies: {', '.join(status['companies'])}")
            print(f"Interval: {status['interval_minutes']} minutes")
            print(f"Status: {status['status']}")
            
            stats = status['last_24h_stats']
            print(f"\nLast 24 Hours:")
            print(f"  Total Runs: {stats.get('total_runs', 0)}")
            print(f"  Successful: {stats.get('successful_runs', 0)}")
            print(f"  Total Jobs: {stats.get('total_jobs', 0)}")
            print(f"  Last Run: {stats.get('last_run', 'Never')}")
            
        elif args.once:
            auto_scraper.run_once()
        else:
            auto_scraper.run_continuously()
            
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
