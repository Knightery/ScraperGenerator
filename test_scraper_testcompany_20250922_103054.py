#!/usr/bin/env python3
"""
Playwright-based job scraper for TestCompany
Generated automatically by AI Navigator
URL: https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers?jobFamily=de769652963501ab29a8b80c0704c3aa
Generated at: 2025-09-22T10:30:54.874652
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
            logging.FileHandler(f'logs/testcompany_scraper.log'),
            logging.StreamHandler()
        ]
    )


def get_scraper_config():
    """Get the scraper configuration for TestCompany."""
    return {
        'company_name': 'TestCompany',
        'scrape_url': 'https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers?jobFamily=de769652963501ab29a8b80c0704c3aa',
        'job_container_selector': 'ul[aria-label^="Page"] > li',
        'title_selector': 'a[data-automation-id="jobTitle"]',
        'url_selector': 'a[data-automation-id="jobTitle"]',
        'description_selector': '',
        'location_selector': '[data-automation-id="locations"] dd',
        'requirements_selector': '',
        'pagination_selector': 'button[data-uxi-element-id="next"]',
        'has_dynamic_loading': True,
        'max_pages': 999  # Unlimited - will stop automatically based on end conditions
    }


def main():
    """Main scraper function."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Starting TestCompany job scraper...")
    
    config = get_scraper_config()
    
    # Initialize database-enabled scraper
    scraper = PlaywrightScraperSync(use_database=True)
    db_manager = DatabaseManager()
    
    # Get company info from database
    company = db_manager.get_company_by_name('TestCompany')
    if not company:
        logger.error("Company 'TestCompany' not found in database")
        print("Error: Company not found in database. Please add the company first.")
        return
    
    # Update last scraped timestamp
    db_manager.update_company_scraper(company['id'], "")
    
    # Scrape jobs and get filtered HTML
    jobs, filtered_html = scraper.scrape_jobs(config['scrape_url'], config)
    
    if jobs:
        logger.info(f"Successfully scraped {len(jobs)} jobs from TestCompany")
        
        # Print summary
        print(f"\n=== SCRAPING RESULTS ===")
        print(f"Company: TestCompany")
        print(f"URL: https://td.wd3.myworkdayjobs.com/en-US/TD_Bank_Careers?jobFamily=de769652963501ab29a8b80c0704c3aa")
        print(f"Jobs found: {len(jobs)}")
        print(f"Jobs saved to database: jobs.db")
        
        # Show sample jobs
        print(f"\n=== SAMPLE JOBS ===")
        for i, job in enumerate(jobs[:3], 1):
            print(f"{i}. {job.get('title', 'No title')}")
            print(f"   Location: {job.get('location', 'Not specified')}")
            print(f"   URL: {job.get('url', 'No URL')}")
            print()
            
        # Optional: Also save as JSON backup if needed
        # output_file = f'testcompany_jobs_{int(datetime.now().timestamp())}.json'
        # with open(output_file, 'w', encoding='utf-8') as f:
        #     json.dump(jobs, f, indent=2, ensure_ascii=False)
        # print(f"Backup JSON saved to: {output_file}")
        
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
