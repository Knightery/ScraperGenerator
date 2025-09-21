#!/usr/bin/env python3
"""
Database utility commands for the job scraper system.
Provides easy access to view and manage jobs in the database.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import List, Dict

from database import DatabaseManager


def list_companies():
    """List all companies in the database."""
    db = DatabaseManager()
    companies = db.get_all_active_companies()
    
    print("\n=== COMPANIES IN DATABASE ===")
    if not companies:
        print("No companies found in database.")
        return
    
    for company in companies:
        print(f"\nCompany: {company['name']}")
        print(f"  ID: {company['id']}")
        print(f"  URL: {company['job_board_url']}")
        print(f"  Status: {company['status']}")
        print(f"  Last Scraped: {company.get('last_scraped', 'Never')}")
        print(f"  Created: {company.get('created_at', 'Unknown')}")


def list_jobs(company_name: str = None, limit: int = 20):
    """List jobs from the database."""
    db = DatabaseManager()
    
    if company_name:
        company = db.get_company_by_name(company_name)
        if not company:
            print(f"Company '{company_name}' not found in database.")
            return
        
        jobs = db.get_jobs_by_company(company['id'], limit)
        print(f"\n=== JOBS FOR {company_name.upper()} (Last {limit}) ===")
    else:
        # Get all recent jobs across all companies
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT j.*, c.name as company_name 
                FROM jobs j 
                JOIN companies c ON j.company_id = c.id 
                ORDER BY j.scraped_at DESC 
                LIMIT ?
            ''', (limit,))
            jobs = [dict(row) for row in cursor.fetchall()]
        print(f"\n=== ALL RECENT JOBS (Last {limit}) ===")
    
    if not jobs:
        print("No jobs found.")
        return
    
    for i, job in enumerate(jobs, 1):
        company_display = job.get('company_name', 'Unknown Company')
        print(f"\n{i}. {job['title']}")
        print(f"   Company: {company_display}")
        print(f"   Location: {job.get('location', 'Not specified')}")
        print(f"   URL: {job['url']}")
        print(f"   Scraped: {job['scraped_at']}")
        if job.get('description'):
            desc = job['description'][:100] + "..." if len(job['description']) > 100 else job['description']
            print(f"   Description: {desc}")


def show_stats(company_name: str = None):
    """Show database statistics."""
    db = DatabaseManager()
    
    with db.get_connection() as conn:
        cursor = conn.cursor()
        
        if company_name:
            company = db.get_company_by_name(company_name)
            if not company:
                print(f"Company '{company_name}' not found in database.")
                return
            
            print(f"\n=== STATISTICS FOR {company_name.upper()} ===")
            
            # Job counts
            cursor.execute('SELECT COUNT(*) as total FROM jobs WHERE company_id = ?', (company['id'],))
            total_jobs = cursor.fetchone()['total']
            
            cursor.execute('''
                SELECT COUNT(*) as recent FROM jobs 
                WHERE company_id = ? AND scraped_at > datetime('now', '-7 days')
            ''', (company['id'],))
            recent_jobs = cursor.fetchone()['recent']
            
            # Scraper stats
            stats = db.get_scraper_stats(company['id'])
            
            print(f"Total Jobs: {total_jobs}")
            print(f"Jobs (Last 7 days): {recent_jobs}")
            print(f"Scraper Runs (Last 7 days): {stats.get('total_runs', 0)}")
            print(f"Successful Runs: {stats.get('successful_runs', 0)}")
            print(f"Average Jobs per Run: {stats.get('avg_jobs_found', 0):.1f}")
            print(f"Last Run: {stats.get('last_run', 'Never')}")
            
        else:
            print("\n=== DATABASE STATISTICS ===")
            
            # Overall stats
            cursor.execute('SELECT COUNT(*) as total FROM companies WHERE status = "active"')
            total_companies = cursor.fetchone()['total']
            
            cursor.execute('SELECT COUNT(*) as total FROM jobs')
            total_jobs = cursor.fetchone()['total']
            
            cursor.execute('''
                SELECT COUNT(*) as recent FROM jobs 
                WHERE scraped_at > datetime('now', '-7 days')
            ''')
            recent_jobs = cursor.fetchone()['recent']
            
            cursor.execute('''
                SELECT COUNT(*) as recent FROM scraper_logs 
                WHERE execution_time > datetime('now', '-7 days')
            ''')
            recent_runs = cursor.fetchone()['recent']
            
            print(f"Active Companies: {total_companies}")
            print(f"Total Jobs: {total_jobs}")
            print(f"Jobs Added (Last 7 days): {recent_jobs}")
            print(f"Scraper Runs (Last 7 days): {recent_runs}")


def export_jobs(company_name: str = None, output_file: str = None):
    """Export jobs to JSON file."""
    db = DatabaseManager()
    
    if company_name:
        company = db.get_company_by_name(company_name)
        if not company:
            print(f"Company '{company_name}' not found in database.")
            return
        
        jobs = db.get_jobs_by_company(company['id'], limit=1000)
        if not output_file:
            output_file = f"{company_name.lower().replace(' ', '_')}_jobs_export.json"
    else:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT j.*, c.name as company_name 
                FROM jobs j 
                JOIN companies c ON j.company_id = c.id 
                ORDER BY j.scraped_at DESC
            ''')
            jobs = [dict(row) for row in cursor.fetchall()]
        
        if not output_file:
            output_file = f"all_jobs_export_{int(datetime.now().timestamp())}.json"
    
    if not jobs:
        print("No jobs to export.")
        return
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)
    
    print(f"Exported {len(jobs)} jobs to {output_file}")


def show_database_info():
    """Show database file information including WAL and SHM files."""
    db = DatabaseManager()
    info = db.get_database_info()
    
    print("\n=== DATABASE FILE INFORMATION ===")
    print(f"Main Database: {info['main_db']}")
    print(f"  Exists: {info['main_db_exists']}")
    if info['main_db_exists']:
        print(f"  Size: {info['main_db_size']:,} bytes ({info['main_db_size']/1024/1024:.1f} MB)")
    
    print(f"\nWAL File: {info['wal_file']}")
    print(f"  Exists: {info['wal_exists']}")
    if info['wal_exists']:
        print(f"  Size: {info['wal_file_size']:,} bytes ({info['wal_file_size']/1024/1024:.1f} MB)")
    
    print(f"\nSHM File: {info['shm_file']}")
    print(f"  Exists: {info['shm_exists']}")
    if info['shm_exists']:
        print(f"  Size: {info['shm_file_size']:,} bytes ({info['shm_file_size']/1024:.1f} KB)")
    
    total_size = info['main_db_size'] + info['wal_file_size'] + info['shm_file_size']
    print(f"\nTotal Database Size: {total_size:,} bytes ({total_size/1024/1024:.1f} MB)")


def checkpoint_wal():
    """Perform WAL checkpoint to merge WAL file back to main database."""
    print("Performing WAL checkpoint...")
    db = DatabaseManager()
    
    # Show before state
    info_before = db.get_database_info()
    wal_size_before = info_before['wal_file_size']
    
    # Perform checkpoint
    db.checkpoint_wal()
    
    # Show after state
    info_after = db.get_database_info()
    wal_size_after = info_after['wal_file_size']
    
    print(f"WAL checkpoint completed!")
    print(f"WAL file size: {wal_size_before:,} bytes → {wal_size_after:,} bytes")
    
    if wal_size_before > wal_size_after:
        saved = wal_size_before - wal_size_after
        print(f"Merged {saved:,} bytes from WAL to main database")
    else:
        print("WAL file size unchanged (likely still in use or small)")


def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Database utilities for job scraper system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python db_utils.py companies                    # List all companies
  python db_utils.py jobs                         # List recent jobs (all companies)
  python db_utils.py jobs --company "Morgan Stanley" # List jobs for specific company
  python db_utils.py stats                        # Show overall statistics
  python db_utils.py stats --company "Goldman Sachs" # Show company statistics
  python db_utils.py export --company "BCG"       # Export company jobs to JSON
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Companies command
    subparsers.add_parser('companies', help='List all companies')
    
    # Jobs command
    jobs_parser = subparsers.add_parser('jobs', help='List jobs')
    jobs_parser.add_argument('--company', help='Company name to filter by')
    jobs_parser.add_argument('--limit', type=int, default=20, help='Number of jobs to show')
    
    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show statistics')
    stats_parser.add_argument('--company', help='Company name to show stats for')
    
    # Export command
    export_parser = subparsers.add_parser('export', help='Export jobs to JSON')
    export_parser.add_argument('--company', help='Company name to export')
    export_parser.add_argument('--output', help='Output file name')
    
    # Database info command
    subparsers.add_parser('dbinfo', help='Show database file information (including WAL/SHM)')
    
    # WAL checkpoint command
    subparsers.add_parser('checkpoint', help='Perform WAL checkpoint (merge WAL to main DB)')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        if args.command == 'companies':
            list_companies()
        elif args.command == 'jobs':
            list_jobs(args.company, args.limit)
        elif args.command == 'stats':
            show_stats(args.company)
        elif args.command == 'export':
            export_jobs(args.company, args.output)
        elif args.command == 'dbinfo':
            show_database_info()
        elif args.command == 'checkpoint':
            checkpoint_wal()
            
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()

