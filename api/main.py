#!/usr/bin/env python3
"""
Vercel serverless function entry point for the Job Scraper Web Interface.
This module adapts the Flask application to work with Vercel's serverless platform.
"""

import json
import os
import sys
import threading
import uuid
from pathlib import Path
from queue import Empty, Queue
from urllib.parse import unquote, urljoin

import requests
from flask import Flask, render_template, request, jsonify, Response
from datetime import datetime
from supabase_database import SupabaseDatabaseManager
import logging
from typing import Dict, Optional

# Add the parent directory to the path to import our modules
current_dir = Path(__file__).parent
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))

# Initialize Flask app
app = Flask(__name__, 
           template_folder=str(parent_dir / 'templates'),
           static_folder=str(parent_dir / 'static'))

app.secret_key = os.environ.get('SECRET_KEY', 'vercel-job-scraper-secret-key')

# Setup logging for Vercel
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Supabase database manager
logger.info("Initializing Supabase database")
try:
    db = SupabaseDatabaseManager()
    logger.info("Supabase database manager initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Supabase database manager: {e}")
    # For production deployment, we require Supabase to be configured
    if os.environ.get('VERCEL_ENV'):
        raise Exception("Supabase configuration required for production deployment")
    else:
        logger.error("Supabase not configured. Please check your environment variables.")
        raise

# In-memory progress channels for create-scraper workflows
progress_channels: Dict[str, Queue] = {}
progress_lock = threading.Lock()
KEEPALIVE_SECONDS = 20


def _register_progress_channel(job_id: str) -> Queue:
    queue = Queue()
    with progress_lock:
        progress_channels[job_id] = queue
    return queue


def _get_progress_channel(job_id: str) -> Optional[Queue]:
    with progress_lock:
        return progress_channels.get(job_id)


def _unregister_progress_channel(job_id: str) -> None:
    with progress_lock:
        progress_channels.pop(job_id, None)

@app.route('/')
def index():
    """Home page showing recent jobs and statistics."""
    try:
        # Get recent jobs and statistics from Supabase
        recent_jobs = db.get_recent_jobs(limit=50)
        stats = db.get_dashboard_stats()
        
        return render_template('index.html', jobs=recent_jobs, stats=stats)
        
    except Exception as e:
        logger.error(f"Error loading home page: {str(e)}")
        return render_template('error.html', error=str(e)), 500


@app.route('/create-scraper')
def create_scraper_page():
    """Interactive workflow for creating a new scraper."""
    return render_template('create_scraper.html')

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
        
        search_result = db.search_jobs(
            search_query=search_query,
            company_filter=company_filter,
            location_filter=location_filter,
            limit=per_page,
            offset=offset
        )

        jobs_list = search_result.get('jobs', [])
        total_jobs = search_result.get('total_count', 0)

        companies_data = db.get_all_active_companies()
        companies = sorted(company['name'] for company in companies_data)

        locations = db.get_top_locations(limit=20)

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
        # Get companies with statistics from Supabase
        companies_list = db.get_companies_with_stats()
        
        return render_template('companies.html', companies=companies_list)
        
    except Exception as e:
        logger.error(f"Error loading companies page: {str(e)}")
        return render_template('error.html', error=str(e)), 500


@app.route('/api/create-scraper', methods=['POST'])
def api_create_scraper():
    """Kick off a background scraper generation workflow."""
    payload = request.get_json(silent=True) or {}
    company = (payload.get('company') or '').strip()
    gemini_key = (payload.get('geminiApiKey') or '').strip()

    if not company:
        return jsonify({'success': False, 'error': 'Company name is required'}), 400

    if not gemini_key:
        return jsonify({'success': False, 'error': 'Gemini API key is required for live search'}), 400

    job_id = str(uuid.uuid4())
    queue = _register_progress_channel(job_id)

    queue.put({
        'type': 'update',
        'stage': 'queued',
        'message': 'Queued and waiting for worker',
        'company': company,
        'timestamp': datetime.utcnow().isoformat()
    })

    def progress(event: Dict):
        try:
            event_payload = dict(event or {})
        except Exception:
            event_payload = {'type': 'error', 'message': 'Malformed progress payload'}

        event_payload.setdefault('company', company)
        event_payload.setdefault('type', event_payload.get('stage', 'update') or 'update')
        event_payload['timestamp'] = datetime.utcnow().isoformat()
        queue.put(event_payload)

    render_url = os.getenv('RENDER_SCRAPER_URL')
    render_token = os.getenv('RENDER_API_KEY')

    if not render_url:
        error_message = 'Render scraper endpoint is not configured'
        logger.error(error_message)
        queue.put({
            'type': 'error',
            'stage': 'error',
            'status': 'error',
            'company': company,
            'message': error_message,
            'timestamp': datetime.utcnow().isoformat()
        })
        queue.put({
            'type': 'finalized',
            'stage': 'finalized',
            'status': 'error',
            'company': company,
            'message': 'Workflow terminated unexpectedly',
            'timestamp': datetime.utcnow().isoformat()
        })
        queue.put(None)
        return jsonify({'success': False, 'error': error_message}), 500

    callback_path = f"/api/create-scraper/callback/{job_id}"
    callback_url = urljoin(request.url_root, callback_path.lstrip('/'))

    headers = {'Content-Type': 'application/json'}
    if render_token:
        headers['Authorization'] = f"Bearer {render_token}"

    render_payload = {
        'company': company,
        'geminiApiKey': gemini_key,
        'jobId': job_id,
        'callbackUrl': callback_url
    }

    try:
        response = requests.post(render_url, json=render_payload, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.exception("Failed to start Render scraper job: %s", exc)
        queue.put({
            'type': 'error',
            'stage': 'error',
            'status': 'error',
            'company': company,
            'message': f'Render request failed: {exc}',
            'timestamp': datetime.utcnow().isoformat()
        })
        queue.put({
            'type': 'finalized',
            'stage': 'finalized',
            'status': 'error',
            'company': company,
            'message': 'Workflow terminated unexpectedly',
            'timestamp': datetime.utcnow().isoformat()
        })
        queue.put(None)
        return jsonify({'success': False, 'error': 'Failed to start Render job'}), 502

    render_response = response.json() if response.content else {}
    queue.put({
        'type': 'update',
        'stage': 'render-dispatch',
        'message': 'Render job accepted',
        'company': company,
        'renderJobId': render_response.get('jobId'),
        'timestamp': datetime.utcnow().isoformat()
    })

    return jsonify({'success': True, 'jobId': job_id, 'render': render_response})


@app.route('/api/create-scraper/callback/<job_id>', methods=['POST'])
def api_create_scraper_callback(job_id: str):
    """Receive progress events from the Render scraper worker."""
    queue = _get_progress_channel(job_id)
    if queue is None:
        logger.warning("Received callback for unknown job %s", job_id)
        return jsonify({'success': False, 'error': 'Job not found'}), 404

    event = request.get_json(silent=True) or {}
    event.setdefault('timestamp', datetime.utcnow().isoformat())
    event.setdefault('jobId', job_id)

    queue.put(event)

    if event.get('type') == 'finalized' or event.get('final') or event.get('status') in {'success', 'error'}:
        queue.put(None)

    return jsonify({'success': True})


@app.route('/api/create-scraper/events/<job_id>')
def api_create_scraper_events(job_id: str):
    """Server-sent events stream for create-scraper progress."""

    def event_stream():
        queue = _get_progress_channel(job_id)
        if queue is None:
            yield f"event: error\ndata: {json.dumps({'status': 'error', 'message': 'Job not found'})}\n\n"
            return

        try:
            while True:
                try:
                    item = queue.get(timeout=KEEPALIVE_SECONDS)
                except Empty:
                    keepalive = {
                        'type': 'keepalive',
                        'timestamp': datetime.utcnow().isoformat(),
                        'jobId': job_id
                    }
                    yield f"event: keepalive\ndata: {json.dumps(keepalive)}\n\n"
                    continue

                if item is None:
                    yield f"event: closed\ndata: {json.dumps({'jobId': job_id})}\n\n"
                    break

                event_type = item.get('type') or 'update'
                payload = dict(item)
                payload['jobId'] = job_id

                try:
                    data = json.dumps(payload)
                except TypeError:
                    payload = {
                        'type': 'error',
                        'status': 'error',
                        'message': 'Non-serializable payload encountered',
                        'jobId': job_id,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                    data = json.dumps(payload)
                    event_type = 'error'

                yield f"event: {event_type}\ndata: {data}\n\n"
        finally:
            _unregister_progress_channel(job_id)

    response = Response(event_stream(), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response

@app.route('/company/<company_name>')
def company_detail(company_name):
    """Detailed view of a specific company and its jobs."""
    try:
        company_name = unquote(company_name)
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
        
        search_result = db.search_jobs(
            search_query=search_query,
            company_filter=company_filter,
            location_filter=location_filter,
            limit=limit,
            offset=0
        )

        jobs_list = search_result.get('jobs', [])

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
        stats = db.get_dashboard_stats()
        top_companies = db.get_top_companies(limit=10)

        return jsonify({
            'success': True,
            'stats': {
                'total_jobs': stats.get('total_jobs', 0),
                'total_companies': stats.get('total_companies', 0),
                'jobs_this_week': stats.get('jobs_this_week', 0),
                'jobs_today': stats.get('jobs_today', 0),
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
    try:
        # Use Supabase health check
        health_status = db.health_check()
        health_status['database_type'] = 'supabase'
        return jsonify(health_status)
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.utcnow().isoformat(),
            'database_type': 'supabase'
        }), 500

# Vercel entry point - the app instance is automatically detected

# For local development
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)