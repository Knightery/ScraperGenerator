# Job Scraper Web Interface

A modern, responsive web interface for viewing and searching scraped job data from your AI-powered job scraper system.

## Quick Start

1. **Install dependencies:**
   ```bash
   pip install flask werkzeug
   # or update all requirements:
   pip install -r requirements.txt
   ```

2. **Start the web server:**
   ```bash
   python run_web.py
   ```

3. **Open your browser to:** http://localhost:5000

## Features

### 🏠 **Dashboard**
- Real-time statistics (total jobs, companies, recent activity)
- Recent job listings preview
- Modern, responsive design

### 🔍 **Job Search & Browse**
- Advanced search by title, description, company, location
- Real-time filtering and pagination
- Responsive job cards with direct apply links

### 🏢 **Company Management**
- View all tracked companies
- Company-specific job listings
- Scraper statistics and performance metrics

### 📊 **Statistics & Analytics**
- System-wide job statistics
- Company performance metrics
- Scraping success rates and history

## Usage Examples

### Basic Usage
```bash
# Start on default port 5000
python run_web.py

# Start on custom port
python run_web.py --port 8080

# Enable debug mode
python run_web.py --debug
```

### Production Usage
```bash
# Allow external connections
python run_web.py --public --port 80

# For VPS deployment
python run_web.py --host 0.0.0.0 --port 5000 --no-browser
```

## API Endpoints

The web interface also provides REST API endpoints:

- `GET /api/jobs/search` - Search jobs with parameters
- `GET /api/stats` - Get system statistics

### API Example
```bash
# Search for jobs
curl "http://localhost:5000/api/jobs/search?q=software&company=Google&limit=10"

# Get statistics
curl "http://localhost:5000/api/stats"
```

## File Structure

```
├── web_app.py              # Main Flask application
├── run_web.py              # Easy startup script
├── templates/              # HTML templates
│   ├── base.html          # Base template
│   ├── index.html         # Home page
│   ├── jobs.html          # Job search page
│   ├── companies.html     # Companies listing
│   ├── company_detail.html # Company details
│   └── error.html         # Error page
└── static/                # Static assets
    ├── css/style.css      # Custom styles
    └── js/main.js         # JavaScript functionality
```

## Technology Stack

- **Backend:** Flask (Python web framework)
- **Frontend:** Bootstrap 5, Vanilla JavaScript
- **Database:** SQLite (same as scraper system)
- **Icons:** Bootstrap Icons
- **Styling:** Custom CSS with modern design

## Configuration

Set environment variables for customization:

```bash
export PORT=5000                    # Server port
export DEBUG=false                  # Debug mode
export SECRET_KEY=your-secret-key   # Flask secret key
```

## Integration

The web interface integrates seamlessly with your existing job scraper system:

- **Database:** Uses the same `jobs.db` SQLite database
- **No Setup Required:** Automatically reads existing scraped data
- **Real-time:** Shows data as soon as scrapers add new jobs
- **Statistics:** Provides insights into scraper performance

## Browser Compatibility

- Chrome/Chromium 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Performance

- **Fast Loading:** Optimized queries and pagination
- **Responsive:** Works on desktop, tablet, and mobile
- **Lightweight:** Minimal dependencies and clean code
- **Caching:** Browser caching for static assets

## Troubleshooting

### No Jobs Showing
- Ensure `jobs.db` exists in the project directory
- Add companies using: `python scrape_cli.py add "Company Name"`
- Check that scrapers have run successfully

### Port Already in Use
```bash
# Use a different port
python run_web.py --port 8080
```

### External Access Issues
```bash
# Allow external connections
python run_web.py --public
```

## Development

To modify the web interface:

1. **Templates:** Edit HTML files in `templates/`
2. **Styling:** Modify `static/css/style.css`
3. **JavaScript:** Update `static/js/main.js`
4. **Backend:** Modify routes in `web_app.py`

Hot reload is available in debug mode:
```bash
python run_web.py --debug
```