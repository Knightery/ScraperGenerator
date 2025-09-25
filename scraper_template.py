#!/usr/bin/env python3
"""
Playwright-based job scraper for {company_name}
Generated automatically by AI Navigator
URL: {scrape_url}
Generated at: {generated_at}
"""

import json
import logging
import sys
import os
from datetime import datetime

# Add the parent directory to the path to import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright_scraper import PlaywrightScraperSync
from database import DatabaseManager


def setup_logging():
    """Setup logging for the scraper."""
    import os
    os.makedirs('logs', exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'logs/{log_filename}'),
            logging.StreamHandler()
        ]
    )


def get_scraper_config():
    """Get the scraper configuration for {company_name}."""
    return {{
        'company_name': '{company_name}',
        'scrape_url': '{scrape_url}',
        'job_container_selector': '{job_container_selector}',
        'title_selector': '{title_selector}',
        'url_selector': '{url_selector}',
        'description_selector': '{description_selector}',
        'location_selector': '{location_selector}',
        'requirements_selector': '{requirements_selector}',
        'pagination_selector': '{pagination_selector}',
        'has_dynamic_loading': {has_dynamic_loading},
        'max_pages': 999  # Unlimited - will stop automatically based on end conditions
    }}

def main():
    """Main scraper function."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Starting {company_name} job scraper...")
    
    config = get_scraper_config()
    
    # Initialize database-enabled scraper
    scraper = PlaywrightScraperSync(use_database=True)
    db_manager = DatabaseManager()
    
    # Get company info from database
    company = db_manager.get_company_by_name('{company_name}')
    if not company:
        logger.error("Company '{company_name}' not found in database")
        print("Error: Company not found in database. Please add the company first.")
        return
    
    # Update last scraped timestamp
    db_manager.update_company_scraper(company['id'], "")
    
    # Scrape jobs and get filtered HTML
    jobs, filtered_html = scraper.scrape_jobs(config['scrape_url'], config)
    
    if jobs:
        logger.info(f"Successfully scraped {{len(jobs)}} jobs from {company_name}")
        
        # Print summary
        print(f"\\n=== SCRAPING RESULTS ===")
        print(f"Company: {company_name}")
        print(f"URL: {scrape_url}")
        print(f"Jobs found: {{len(jobs)}}")
        print(f"Jobs saved to database: jobs.db")
        
        # Show sample jobs
        print(f"\\n=== SAMPLE JOBS ===")
        for i, job in enumerate(jobs[:3], 1):
            print(f"{{i}}. {{job.get('title', 'No title')}}")
            print(f"   Location: {{job.get('location', 'Not specified')}}")
            print(f"   URL: {{job.get('url', 'No URL')}}")
            print()
        
    else:
        logger.warning("No jobs found - scraper may need adjustment")
        print("No jobs found. The scraper configuration may need to be adjusted.")
        
        # Log failed scraper execution
        db_manager.log_scraper_execution(
            company['id'], 
            0, 
            success=False,
            error_message="No jobs found"
        )

if __name__ == "__main__":
    main()
