#!/usr/bin/env python3
"""
Enhanced CLI for the Playwright-based job scraper system.
Demonstrates the complete workflow from search to scraper generation.
"""

import argparse
import json
import logging
import os
import sys

from main_scraper import CompanyJobScraper
from supabase_database import SupabaseDatabaseManager
from search_engine import SearchEngine
from ai_navigator import AINavigator
from playwright_scraper import PlaywrightScraperSync
from dotenv import load_dotenv

load_dotenv()

def setup_logging(verbose: bool = False):
    """Setup logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('cli.log'),
            logging.StreamHandler()
        ]
    )

def add_company_command(args):
    """Add a new company to the scraping system."""
    print(f"\n=== Adding Company: {args.company} ===")
    
    scraper = CompanyJobScraper()
    success = scraper.add_company(args.company)
    
    if success:
        print(f"✓ Successfully added {args.company} to the scraping system")
        print(f"✓ Scraper configuration and script generated")
        print(f"✓ Company is now ready for automated scraping")
        
        # Show generated files
        config_file = f"{args.company.lower().replace(' ', '_')}_config.json"
        script_file = os.path.join("scrapers", f"{args.company.lower().replace(' ', '_')}_scraper.py")
        
        if os.path.exists(config_file):
            print(f"✓ Configuration saved to: {config_file}")
        if os.path.exists(script_file):
            print(f"✓ Standalone scraper saved to: {script_file}")
            
    else:
        print(f"✗ Failed to add {args.company}")
        print("Check the logs for more details")


def scrape_company_command(args):
    """Scrape jobs for a specific company."""
    print(f"\n=== Scraping Jobs for: {args.company} ===")
    
    scraper = CompanyJobScraper()
    jobs = scraper.scrape_company(args.company)
    
    if jobs:
        print(f"✓ Successfully scraped {len(jobs)} jobs from {args.company}")
        
        # Show sample jobs
        print("\n=== Sample Jobs ===")
        for i, job in enumerate(jobs[:3], 1):
            print(f"{i}. {job.get('title', 'No title')}")
            print(f"   Location: {job.get('location', 'Not specified')}")
            print(f"   URL: {job.get('url', 'No URL')}")
            print()
            
        # Save results
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(jobs, f, indent=2, ensure_ascii=False)
            print(f"✓ Results saved to: {args.output}")
            
    else:
        print(f"✗ No jobs found for {args.company}")
        print("The scraper configuration may need adjustment")

def test_workflow_command(args):
    """Test the complete workflow with a company."""
    print(f"\n=== Testing Complete Workflow for: {args.company} ===")
    
    # Step 1: Search for company job board
    print("\n1. Searching for company job board...")
    search_engine = SearchEngine()
    job_board_url = search_engine.search_company_jobs(args.company)
    
    if not job_board_url:
        print(f"✗ Could not find job board for {args.company}")
        return
    
    print(f"✓ Found job board: {job_board_url}")
    
    # Step 2: AI navigation and analysis
    print("\n2. AI analyzing job board structure...")
    gemini_api_key = os.getenv('GEMINI_API_KEY')
    ai_navigator = AINavigator(search_engine=search_engine, company_name=args.company, gemini_api_key=gemini_api_key)
    analysis = ai_navigator.analyze_job_board(job_board_url)
    
    if "error" in analysis:
        print(f"✗ Analysis failed: {analysis['error']}")
        return
    
    print("✓ AI analysis completed")
    print(f"  - Job container selector: {analysis.get('job_container_selector', 'Not found')}")
    print(f"  - Title selector: {analysis.get('title_selector', 'Not found')}")
    print(f"  - URL selector: {analysis.get('url_selector', 'Not found')}")
    print(f"  - Confidence score: {analysis.get('confidence_score', 0):.2f}")
    
    # Step 3: Generate scraper configuration
    print("\n3. Generating scraper configuration...")
    scraper_config = ai_navigator.generate_scraper_config(
        args.company, job_board_url, analysis
    )
    
    print("✓ Scraper configuration generated")
    
    # Step 4: Test the scraper
    print("\n4. Testing scraper with Playwright...")
    scraper = PlaywrightScraperSync()
    
    # First test selectors
    selectors = {
        'job_container_selector': scraper_config.get('job_container_selector', ''),
        'title_selector': scraper_config.get('title_selector', ''),
        'url_selector': scraper_config.get('url_selector', ''),
    }
    
    selector_results = scraper.test_selectors(job_board_url, selectors)
    
    if 'error' in selector_results:
        print(f"✗ Selector testing failed: {selector_results['error']}")
        return
    
    print("✓ Selector testing completed")
    for selector_name, result in selector_results.get('results', {}).items():
        if result.get('success'):
            print(f"  - {selector_name}: ✓ ({result.get('elements_found', 0)} elements)")
        else:
            print(f"  - {selector_name}: ✗ (no elements found)")
    
    # Step 5: Scrape actual jobs
    print("\n5. Scraping jobs...")
    test_config = scraper_config.copy()
    test_config['max_pages'] = 1  # Only test first page
    
    jobs, filtered_html = scraper.scrape_jobs(job_board_url, test_config)
    
    if jobs:
        print(f"✓ Successfully scraped {len(jobs)} jobs")
        
        # Show sample jobs
        print("\n=== Sample Jobs ===")
        for i, job in enumerate(jobs[:3], 1):
            print(f"{i}. {job.get('title', 'No title')}")
            print(f"   Location: {job.get('location', 'Not specified')}")
            print(f"   URL: {job.get('url', 'No URL')}")
            print()
            
        # Step 6: Generate standalone scraper script
        print("\n6. Generating standalone scraper script...")
        scraper_script = ai_navigator.generate_scraper_script(
            args.company, job_board_url, analysis
        )
        
        # Create scrapers directory if it doesn't exist
        os.makedirs("scrapers", exist_ok=True)
        
        # Save files
        config_file = f"{args.company.lower().replace(' ', '_')}_test_config.json"
        script_file = os.path.join("scrapers", f"{args.company.lower().replace(' ', '_')}_test_scraper.py")
        
        with open(config_file, 'w') as f:
            json.dump(scraper_config, f, indent=2)
        
        with open(script_file, 'w') as f:
            f.write(scraper_script)
        
        print(f"✓ Configuration saved to: {config_file}")
        print(f"✓ Standalone scraper saved to: {script_file}")
        
        print(f"\n=== Workflow Complete ===")
        print(f"The complete workflow has been successfully tested for {args.company}")
        print(f"You can now run the standalone scraper with: python {script_file}")
        
    else:
        print("✗ No jobs found - scraper may need adjustment")

def list_companies_command(args):
    """List all companies in the database."""
    print("\n=== Registered Companies ===")
    
    db = SupabaseDatabaseManager()
    companies = db.get_all_active_companies()
    
    if companies:
        for i, company in enumerate(companies, 1):
            print(f"{i}. {company['name']}")
            print(f"   URL: {company['job_board_url']}")
            print(f"   Added: {company.get('created_at', 'Unknown')}")
            print()
    else:
        print("No companies registered yet.")
        print("Use 'python scrape_cli.py add <company_name>' to add a company.")


def stats_command(args):
    """Show statistics for a company."""
    print(f"\n=== Statistics for: {args.company} ===")
    
    scraper = CompanyJobScraper()
    stats = scraper.get_company_stats(args.company)
    
    if "error" in stats:
        print(f"✗ {stats['error']}")
        return
    
    company = stats['company']
    scraper_stats = stats['stats']
    recent_jobs = stats['recent_jobs']
    
    print(f"Company: {company['name']}")
    print(f"Job Board URL: {company['job_board_url']}")
    print(f"Status: {company['status']}")
    print(f"Last Scraped: {company.get('last_scraped', 'Never')}")
    
    print(f"\nScraper Statistics (last 7 days):")
    print(f"Total Runs: {scraper_stats.get('total_runs', 0)}")
    print(f"Successful Runs: {scraper_stats.get('successful_runs', 0)}")
    print(f"Average Jobs Found: {scraper_stats.get('avg_jobs_found', 0):.1f}")
    print(f"Last Run: {scraper_stats.get('last_run', 'Never')}")
    
    print(f"\nRecent Jobs ({len(recent_jobs)}):")
    for i, job in enumerate(recent_jobs[:5], 1):
        print(f"{i}. {job['title']}")
        print(f"   Location: {job.get('location', 'Not specified')}")
        print(f"   Scraped: {job['scraped_at']}")
        print()


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Playwright-based Job Scraper CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scrape_cli.py test-workflow "Morgan Stanley"    # Test complete workflow
  python scrape_cli.py add "Goldman Sachs"               # Add company to system
  python scrape_cli.py scrape "Morgan Stanley"           # Scrape jobs for company
  python scrape_cli.py list                              # List all companies
  python scrape_cli.py stats "Morgan Stanley"            # Show company statistics
        """
    )
    
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Enable verbose logging')
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Test workflow command
    test_parser = subparsers.add_parser('test-workflow', 
                                       help='Test complete workflow for a company')
    test_parser.add_argument('company', help='Company name to test')
    
    # Add company command
    add_parser = subparsers.add_parser('add', 
                                      help='Add a company to the scraping system')
    add_parser.add_argument('company', help='Company name to add')
    
    # Scrape company command
    scrape_parser = subparsers.add_parser('scrape', 
                                         help='Scrape jobs for a company')
    scrape_parser.add_argument('company', help='Company name to scrape')
    scrape_parser.add_argument('-o', '--output', 
                              help='Output file for scraped jobs (JSON)')
    
    # List companies command
    subparsers.add_parser('list', help='List all registered companies')
    
    # Stats command
    stats_parser = subparsers.add_parser('stats', 
                                        help='Show statistics for a company')
    stats_parser.add_argument('company', help='Company name')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    setup_logging(args.verbose)
    
    try:
        if args.command == 'test-workflow':
            test_workflow_command(args)
        elif args.command == 'add':
            add_company_command(args)
        elif args.command == 'scrape':
            scrape_company_command(args)
        elif args.command == 'list':
            list_companies_command(args)
        elif args.command == 'stats':
            stats_command(args)
            
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user")
    except Exception as e:
        print(f"\nError: {str(e)}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
