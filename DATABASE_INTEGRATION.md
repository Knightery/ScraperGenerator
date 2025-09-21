# Database Integration for Job Scrapers

## Overview

The job scraper system has been enhanced to integrate with the `jobs.db` SQLite database instead of saving jobs as JSON files. This provides better data management, deduplication by URL, and persistent storage.

## Key Changes Made

### 1. Enhanced DatabaseManager (`database.py`)

**New Method: `add_jobs_batch()`**
- Adds multiple jobs in a single transaction
- Automatic deduplication by URL (using UNIQUE constraint)
- Returns statistics: `{'added': int, 'duplicates': int, 'errors': int}`
- Handles missing or invalid job data gracefully

**New Method: `get_company_scraper_config()`**
- Retrieves stored scraper configuration for a company
- Supports both JSON config and script text storage

### 2. Enhanced PlaywrightScraperSync (`playwright_scraper.py`)

**Database Integration**
- New parameter: `use_database=True` enables database storage
- Automatically saves scraped jobs to database when enabled
- Logs scraper execution results (success/failure, job counts)
- Maintains backward compatibility with JSON-only mode

**Usage:**
```python
# Database-enabled scraper
scraper = PlaywrightScraperSync(use_database=True)
jobs, html = scraper.scrape_jobs(url, config)
# Jobs are automatically saved to database
```

### 3. Updated AI Navigator (`ai_navigator.py`)

**Modified Scraper Template**
- Generated scripts now use database-integrated scrapers
- No longer saves JSON files by default (commented backup option)
- Includes proper error handling and logging
- Updates company's `last_scraped` timestamp

**Template Changes:**
- Imports `DatabaseManager`
- Uses `PlaywrightScraperSync(use_database=True)`
- Validates company exists in database
- Logs failed executions

### 4. Updated CompanyJobScraper (`main_scraper.py`)

**Database-First Workflow**
- Returns jobs from database after scraping
- Logs scraper execution results
- Better error handling and reporting
- Maintains existing API compatibility

### 5. New Database Utilities (`db_utils.py`)

**Commands Available:**
- `python db_utils.py companies` - List all companies
- `python db_utils.py jobs` - List recent jobs (all companies)
- `python db_utils.py jobs --company "Company Name"` - List company jobs
- `python db_utils.py stats` - Show database statistics
- `python db_utils.py stats --company "Company Name"` - Show company stats
- `python db_utils.py export --company "Company Name"` - Export to JSON

## Database Schema

The existing schema supports the integration:

```sql
-- Companies table
CREATE TABLE companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    job_board_url TEXT NOT NULL,
    scraper_script TEXT,
    last_scraped TIMESTAMP,
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Jobs table (URL is UNIQUE for deduplication)
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,  -- Prevents duplicates
    description TEXT,
    requirements TEXT,
    location TEXT,
    posted_date DATE,
    scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (company_id) REFERENCES companies (id)
);

-- Scraper execution logs
CREATE TABLE scraper_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER,
    execution_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    jobs_found INTEGER,
    success BOOLEAN,
    error_message TEXT,
    FOREIGN KEY (company_id) REFERENCES companies (id)
);
```

## Workflow Changes

### Before (JSON-based):
1. Search → AI Analysis → Generate Script
2. Generated script scrapes jobs
3. Jobs saved as timestamped JSON files
4. No deduplication, no persistence management

### After (Database-integrated):
1. Search → AI Analysis → Generate Script
2. Generated script uses database-integrated scraper
3. Jobs automatically saved to `jobs.db` with URL-based deduplication
4. Execution results logged for monitoring
5. Easy querying and management via database utilities

## Migration Guide

### For Existing Companies:
1. Existing generated scripts will continue to work
2. Re-generate scripts to get database integration:
   ```bash
   python new_cli.py add "Company Name"  # Re-adds with new template
   ```

### For New Companies:
- All new companies automatically get database-integrated scrapers
- No changes needed to existing workflow

### Accessing Data:
```python
# Get jobs from database instead of JSON files
from database import DatabaseManager

db = DatabaseManager()
company = db.get_company_by_name("Boston Consulting Group")
jobs = db.get_jobs_by_company(company['id'], limit=50)
```

## Benefits

1. **Deduplication**: URL-based deduplication prevents duplicate job entries
2. **Persistence**: All jobs stored in single database file
3. **Monitoring**: Scraper execution logs for debugging and monitoring
4. **Querying**: SQL-based querying for complex data analysis
5. **Statistics**: Built-in statistics and reporting
6. **Backup**: Easy database backup and export options
7. **Scalability**: Better performance for large datasets

## Commands for Testing

```bash
# Test the complete workflow with database integration
python new_cli.py test-workflow "Goldman Sachs"

# Add a company (generates database-integrated scraper)
python new_cli.py add "Morgan Stanley"

# Scrape jobs (saves to database)
python new_cli.py scrape "Morgan Stanley"

# View database contents
python db_utils.py companies
python db_utils.py jobs --company "Morgan Stanley"
python db_utils.py stats

# Export data
python db_utils.py export --company "Morgan Stanley"
```

## Backward Compatibility

- Existing JSON-based workflow still supported
- Old generated scripts continue to work
- New features are opt-in via `use_database=True` parameter
- Database utilities provide JSON export for migration needs

The integration maintains full backward compatibility while providing enhanced functionality for new deployments.

