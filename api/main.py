#!/usr/bin/env python3
"""
Vercel serverless function entry point for the Job Scraper Web Interface.
This module adapts the Flask application to work with Vercel's serverless platform.
"""

import os
import sys
from pathlib import Path

# Add the parent directory to the path to import our modules
current_dir = Path(__file__).parent
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))

from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime, timedelta
from database import DatabaseManager
import logging

# Initialize Flask app
app = Flask(__name__, 
           template_folder=str(parent_dir / 'templates'),
           static_folder=str(parent_dir / 'static'))

app.secret_key = os.environ.get('SECRET_KEY', 'vercel-job-scraper-secret-key')

# Setup logging for Vercel
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration for serverless
DB_PATH = os.environ.get('DATABASE_URL', str(parent_dir / 'jobs.db'))

class VercelDatabaseManager:
    """Database manager adapted for Vercel serverless environment."""
    
    def __init__(self):
        self.db_path = DB_PATH
        self._ensure_database()
    
    def _ensure_database(self):
        """Ensure database exists and is initialized."""
        try:
            if not os.path.exists(self.db_path):
                logger.warning(f"Database not found at {self.db_path}. Creating empty database.")
                # Create minimal database structure
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute('''
                        CREATE TABLE IF NOT EXISTS companies (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT UNIQUE NOT NULL,
                            url TEXT NOT NULL,
                            status TEXT DEFAULT 'active',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')
                    conn.execute('''
                        CREATE TABLE IF NOT EXISTS jobs (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            company_id INTEGER NOT NULL,
                            title TEXT NOT NULL,
                            url TEXT NOT NULL,
                            location TEXT,
                            description TEXT,
                            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (company_id) REFERENCES companies (id),
                            UNIQUE(company_id, title, url)
                        )
                    ''')
                    conn.commit()
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
    
    def get_connection(self):
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_company_by_name(self, name):
        """Get company by name."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM companies WHERE name = ?', (name,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting company by name: {e}")
            return None
    
    def get_jobs_by_company(self, company_id, limit=100):
        """Get jobs for a specific company."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT * FROM jobs 
                    WHERE company_id = ? 
                    ORDER BY scraped_at DESC 
                    LIMIT ?
                ''', (company_id, limit))
                return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Error getting jobs by company: {e}")
            return []
    
    def get_scraper_stats(self, company_id):
        """Get scraper statistics for a company."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) as total FROM jobs WHERE company_id = ?', (company_id,))
                total_jobs = cursor.fetchone()['total']
                
                cursor.execute('''
                    SELECT COUNT(*) as recent FROM jobs 
                    WHERE company_id = ? AND scraped_at > datetime('now', '-7 days')
                ''', (company_id,))
                recent_jobs = cursor.fetchone()['recent']
                
                return {
                    'total_jobs': total_jobs,
                    'recent_jobs': recent_jobs
                }
        except Exception as e:
            logger.error(f"Error getting scraper stats: {e}")
            return {'total_jobs': 0, 'recent_jobs': 0}

# Initialize database manager
db = VercelDatabaseManager()

@app.route('/')
def index():
    """Home page showing recent jobs and statistics."""
    try:
        # Get recent jobs (last 50)
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT j.*, c.name as company_name
                FROM jobs j
                JOIN companies c ON j.company_id = c.id
                WHERE c.status = 'active'
                ORDER BY j.scraped_at DESC
                LIMIT 50
            ''')
            recent_jobs = [dict(row) for row in cursor.fetchall()]
            
            # Get statistics
            cursor.execute('SELECT COUNT(*) as total FROM jobs')
            total_jobs = cursor.fetchone()['total']
            
            cursor.execute('SELECT COUNT(*) as total FROM companies WHERE status = "active"')
            total_companies = cursor.fetchone()['total']
            
            cursor.execute('''
                SELECT COUNT(*) as recent FROM jobs 
                WHERE scraped_at > datetime('now', '-7 days')
            ''')
            jobs_this_week = cursor.fetchone()['recent']
            
            cursor.execute('''
                SELECT COUNT(*) as recent FROM jobs 
                WHERE scraped_at > datetime('now', '-1 day')
            ''')
            jobs_today = cursor.fetchone()['recent']
        
        stats = {
            'total_jobs': total_jobs,
            'total_companies': total_companies,
            'jobs_this_week': jobs_this_week,
            'jobs_today': jobs_today
        }
        
        return render_template('index.html', jobs=recent_jobs, stats=stats)
        
    except Exception as e:
        logger.error(f"Error loading home page: {str(e)}")
        return render_template('error.html', error=str(e)), 500

@app.route('/jobs')
def jobs():
    """Jobs page with search and filtering."""
    try:
        # Get query parameters
        company_filter = request.args.get('company', '')
        search_query = request.args.get('search', '')
        location_filter = request.args.get('location', '')
        page = int(request.args.get('page', 1))
        per_page = 20
        offset = (page - 1) * per_page
        
        # Build SQL query
        sql = '''
            SELECT j.*, c.name as company_name
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE c.status = 'active'
        '''
        params = []
        
        if company_filter:
            sql += ' AND c.name = ?'
            params.append(company_filter)
            
        if search_query:
            sql += ' AND (j.title LIKE ? OR j.description LIKE ?)'
            params.extend([f'%{search_query}%', f'%{search_query}%'])
            
        if location_filter:
            sql += ' AND j.location LIKE ?'
            params.append(f'%{location_filter}%')
        
        # Get total count for pagination
        count_sql = sql.replace('SELECT j.*, c.name as company_name', 'SELECT COUNT(*)')
        
        sql += ' ORDER BY j.scraped_at DESC LIMIT ? OFFSET ?'
        params.extend([per_page, offset])
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Get jobs
            cursor.execute(sql, params)
            jobs_list = [dict(row) for row in cursor.fetchall()]
            
            # Get total count
            cursor.execute(count_sql, params[:-2])  # Remove LIMIT and OFFSET params
            total_jobs = cursor.fetchone()[0]
            
            # Get companies for filter dropdown
            cursor.execute('SELECT name FROM companies WHERE status = "active" ORDER BY name')
            companies = [row['name'] for row in cursor.fetchall()]
            
            # Get unique locations for filter dropdown (top 20)
            cursor.execute('''
                SELECT location, COUNT(*) as count
                FROM jobs j
                JOIN companies c ON j.company_id = c.id
                WHERE c.status = 'active' AND j.location IS NOT NULL AND j.location != ''
                GROUP BY location
                ORDER BY count DESC
                LIMIT 20
            ''')
            locations = [row['location'] for row in cursor.fetchall()]
        
        # Calculate pagination
        total_pages = (total_jobs + per_page - 1) // per_page
        has_prev = page > 1
        has_next = page < total_pages
        
        pagination = {
            'page': page,
            'per_page': per_page,
            'total': total_jobs,
            'total_pages': total_pages,
            'has_prev': has_prev,
            'has_next': has_next,
            'prev_num': page - 1 if has_prev else None,
            'next_num': page + 1 if has_next else None
        }
        
        return render_template('jobs.html', 
                             jobs=jobs_list, 
                             companies=companies,
                             locations=locations,
                             pagination=pagination,
                             filters={
                                 'company': company_filter,
                                 'search': search_query,
                                 'location': location_filter
                             })
        
    except Exception as e:
        logger.error(f"Error loading jobs page: {str(e)}")
        return render_template('error.html', error=str(e)), 500

@app.route('/companies')
def companies():
    """Companies page showing all tracked companies."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    c.*,
                    COUNT(j.id) as job_count,
                    MAX(j.scraped_at) as last_job_scraped
                FROM companies c
                LEFT JOIN jobs j ON c.id = j.company_id
                WHERE c.status = 'active'
                GROUP BY c.id
                ORDER BY c.name
            ''')
            companies_list = [dict(row) for row in cursor.fetchall()]
        
        return render_template('companies.html', companies=companies_list)
        
    except Exception as e:
        logger.error(f"Error loading companies page: {str(e)}")
        return render_template('error.html', error=str(e)), 500

@app.route('/company/<company_name>')
def company_detail(company_name):
    """Detailed view of a specific company and its jobs."""
    try:
        company = db.get_company_by_name(company_name)
        if not company:
            return render_template('error.html', error=f"Company '{company_name}' not found"), 404
        
        # Get company jobs
        jobs_list = db.get_jobs_by_company(company['id'], limit=100)
        
        # Get company statistics
        stats = db.get_scraper_stats(company['id'])
        
        return render_template('company_detail.html', 
                             company=company, 
                             jobs=jobs_list, 
                             stats=stats)
        
    except Exception as e:
        logger.error(f"Error loading company detail page: {str(e)}")
        return render_template('error.html', error=str(e)), 500

@app.route('/api/jobs/search')
def api_jobs_search():
    """API endpoint for job search with JSON response."""
    try:
        search_query = request.args.get('q', '')
        company_filter = request.args.get('company', '')
        location_filter = request.args.get('location', '')
        limit = min(int(request.args.get('limit', 50)), 100)  # Max 100 results
        
        sql = '''
            SELECT j.*, c.name as company_name
            FROM jobs j
            JOIN companies c ON j.company_id = c.id
            WHERE c.status = 'active'
        '''
        params = []
        
        if company_filter:
            sql += ' AND c.name = ?'
            params.append(company_filter)
            
        if search_query:
            sql += ' AND (j.title LIKE ? OR j.description LIKE ?)'
            params.extend([f'%{search_query}%', f'%{search_query}%'])
            
        if location_filter:
            sql += ' AND j.location LIKE ?'
            params.append(f'%{location_filter}%')
        
        sql += ' ORDER BY j.scraped_at DESC LIMIT ?'
        params.append(limit)
        
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            jobs_list = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'jobs': jobs_list,
            'count': len(jobs_list)
        })
        
    except Exception as e:
        logger.error(f"Error in API job search: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/stats')
def api_stats():
    """API endpoint for system statistics."""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Overall statistics
            cursor.execute('SELECT COUNT(*) as total FROM jobs')
            total_jobs = cursor.fetchone()['total']
            
            cursor.execute('SELECT COUNT(*) as total FROM companies WHERE status = "active"')
            total_companies = cursor.fetchone()['total']
            
            cursor.execute('''
                SELECT COUNT(*) as recent FROM jobs 
                WHERE scraped_at > datetime('now', '-7 days')
            ''')
            jobs_this_week = cursor.fetchone()['recent']
            
            cursor.execute('''
                SELECT COUNT(*) as recent FROM jobs 
                WHERE scraped_at > datetime('now', '-1 day')
            ''')
            jobs_today = cursor.fetchone()['recent']
            
            # Top companies by job count
            cursor.execute('''
                SELECT c.name, COUNT(j.id) as job_count
                FROM companies c
                LEFT JOIN jobs j ON c.id = j.company_id
                WHERE c.status = 'active'
                GROUP BY c.id, c.name
                ORDER BY job_count DESC
                LIMIT 10
            ''')
            top_companies = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'stats': {
                'total_jobs': total_jobs,
                'total_companies': total_companies,
                'jobs_this_week': jobs_this_week,
                'jobs_today': jobs_today,
                'top_companies': top_companies
            }
        })
        
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.errorhandler(404)
def not_found(error):
    return render_template('error.html', error="Page not found"), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', error="Internal server error"), 500

# Health check endpoint for Vercel
@app.route('/api/health')
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'database': 'connected' if os.path.exists(DB_PATH) else 'not_found'
    })

# Vercel entry point - the app instance is automatically detected

# For local development
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)