# VPS Auto-Scraper Deployment Guide

## Quick Start for VPS

### 1. Setup on VPS

```bash
# Clone/upload your project to VPS
cd /path/to/ScrapyLinkedIN

# Install dependencies
pip install -r requirements.txt

# Install playwright browsers
playwright install firefox

# Create necessary directories
mkdir -p scrapers logs

# Test the system
python db_utils.py companies  # Check if companies exist
```

### 2. Add Companies (if not already done)

```bash
# Add your companies
python new_cli.py add "Goldman Sachs"
python new_cli.py add "Morgan Stanley" 
python new_cli.py add "Boston Consulting Group"

# Verify scrapers were created
ls scrapers/
```

### 3. Start Auto-Scraper in Screen

```bash
# Start a new screen session
screen -S auto_scraper

# Run the auto-scraper (runs every hour by default)
python auto_scraper.py

# Detach from screen (Ctrl+A then D)
# The scraper will keep running in the background
```

### 4. Monitor and Manage

```bash
# Check status
python auto_scraper.py --status

# View recent jobs
python db_utils.py jobs --limit 50

# View company statistics
python db_utils.py stats

# Reattach to screen to see live output
screen -r auto_scraper

# List all screen sessions
screen -ls
```

## Command Options

### Auto-Scraper Commands

```bash
# Run continuously (default: every 60 minutes)
python auto_scraper.py

# Run with custom interval (every 30 minutes)
python auto_scraper.py --interval 30

# Run once and exit (for testing)
python auto_scraper.py --once

# Check current status
python auto_scraper.py --status
```

### Database Utilities

```bash
# View all companies
python db_utils.py companies

# View recent jobs from all companies
python db_utils.py jobs --limit 100

# View jobs from specific company
python db_utils.py jobs --company "Goldman Sachs"

# View statistics
python db_utils.py stats
python db_utils.py stats --company "Morgan Stanley"

# Export jobs to JSON
python db_utils.py export --company "BCG"

# Show database file info (including WAL/SHM files)
python db_utils.py dbinfo

# Perform WAL checkpoint (merge WAL to main DB)
python db_utils.py checkpoint
```

## File Structure

```
ScrapyLinkedIN/
├── auto_scraper.py          # Main auto-scraper service
├── jobs.db                  # SQLite database with all jobs
├── jobs.db-wal             # WAL (Write-Ahead Log) file
├── jobs.db-shm             # Shared memory file
├── scrapers/               # Generated scraper scripts
│   ├── goldman_sachs_scraper.py
│   ├── morgan_stanley_scraper.py
│   └── boston_consulting_group_scraper.py
├── logs/                   # Log files
│   ├── auto_scraper.log    # Main auto-scraper logs
│   ├── goldman_sachs_scraper.log
│   └── morgan_stanley_scraper.log
└── ...
```

## Auto-Scraper Features

### Intelligent Scheduling
- Runs all company scrapers sequentially
- 10-second delay between companies
- 30-minute timeout per scraper
- Automatic retry and error handling

### Smart Pagination
- Automatically scrapes ALL available pages
- Stops when:
  - No "next page" button found
  - Button is disabled/hidden
  - No jobs found on consecutive pages
  - 80%+ duplicate jobs detected (end of results)

### Monitoring & Logging
- Detailed logs for each scraper run
- Database logging of all executions
- Status reports after each run
- 24-hour activity summaries

### Error Handling
- Graceful handling of scraper failures
- Timeout protection
- Continues with other companies if one fails
- Detailed error logging

## Production Tips

### 1. System Resources
```bash
# Monitor system resources
htop
df -h  # Check disk space

# The scraper uses:
# - ~200MB RAM per browser instance
# - Minimal CPU when not actively scraping
# - Log files grow over time (rotate as needed)
```

### 2. Log Management
```bash
# View live auto-scraper logs
tail -f logs/auto_scraper.log

# View specific company logs
tail -f logs/goldman_sachs_scraper.log

# Rotate logs periodically (add to cron if needed)
find logs/ -name "*.log" -size +100M -delete
```

### 3. Database Management
```bash
# Check database files (including WAL/SHM)
python db_utils.py dbinfo

# Database sizes
ls -lh jobs.db*

# Backup database (include all files)
cp jobs.db* backup/
# OR create a complete backup
python db_utils.py checkpoint  # Merge WAL first
cp jobs.db jobs_backup_$(date +%Y%m%d).db

# Clean old logs (optional)
sqlite3 jobs.db "DELETE FROM scraper_logs WHERE execution_time < datetime('now', '-30 days')"

# Optimize database (merge WAL file)
python db_utils.py checkpoint
```

### 4. Screen Management
```bash
# List all screen sessions
screen -ls

# Reattach to auto-scraper
screen -r auto_scraper

# Kill screen session if needed
screen -S auto_scraper -X quit

# Start new session if needed
screen -S auto_scraper -dm python auto_scraper.py
```

## Troubleshooting

### Common Issues

1. **Playwright Browser Issues**
   ```bash
   # Reinstall browsers
   playwright install firefox
   ```

2. **Permission Issues**
   ```bash
   # Fix permissions
   chmod +x auto_scraper.py
   chmod -R 755 scrapers/
   ```

3. **Database Lock Issues**
   ```bash
   # Check if any processes are using the database
   lsof jobs.db
   ```

4. **Memory Issues**
   ```bash
   # Increase swap if needed on small VPS
   sudo fallocate -l 2G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   ```

### Monitoring Commands

```bash
# Check if auto-scraper is running
ps aux | grep auto_scraper

# Check recent database activity
python db_utils.py stats

# Check last 10 scraper runs
sqlite3 jobs.db "SELECT * FROM scraper_logs ORDER BY execution_time DESC LIMIT 10"

# Check jobs added in last hour
sqlite3 jobs.db "SELECT COUNT(*) FROM jobs WHERE scraped_at > datetime('now', '-1 hour')"
```

## Integration with Website

The `jobs.db` SQLite database can be easily integrated with your website:

```python
# Example: Get recent jobs for website
import sqlite3

def get_recent_jobs(limit=100):
    conn = sqlite3.connect('jobs.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT j.*, c.name as company_name 
        FROM jobs j 
        JOIN companies c ON j.company_id = c.id 
        ORDER BY j.scraped_at DESC 
        LIMIT ?
    ''', (limit,))
    
    jobs = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jobs
```

The auto-scraper will continuously populate this database with fresh job listings every hour!
