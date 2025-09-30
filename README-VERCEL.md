# Vercel Deployment Guide

This guide explains how to deploy the Job Scraper Web Interface to Vercel as a serverless application.

## Prerequisites

1. **Vercel Account**: Sign up at [vercel.com](https://vercel.com)
2. **Vercel CLI** (optional): Install with `npm i -g vercel`
3. **Database**: You'll need a way to access your SQLite database in the cloud

## Project Structure for Vercel

The project has been configured with the following structure for Vercel deployment:

```
├── api/
│   └── index.py          # Main serverless function entry point
├── static/               # Static assets (CSS, JS)
│   ├── css/
│   └── js/
├── templates/            # Jinja2 templates
├── vercel.json          # Vercel deployment configuration
├── requirements-vercel.txt  # Minimal dependencies for web interface
└── README-VERCEL.md     # This file
```

## Quick Deployment

### Method 1: Using Vercel Dashboard (Recommended)

1. **Connect Repository**:
   - Go to [vercel.com/dashboard](https://vercel.com/dashboard)
   - Click "New Project"
   - Import your GitHub repository

2. **Configure Build Settings**:
   - Framework Preset: `Other`
   - Root Directory: `./` (leave empty)
   - Build Command: (leave empty)
   - Output Directory: `./`

3. **Environment Variables** (see section below)

4. **Deploy**: Click "Deploy"

### Method 2: Using Vercel CLI

```bash
# Install Vercel CLI globally
npm i -g vercel

# Login to Vercel
vercel login

# Deploy from your project directory
cd /path/to/your/project
vercel

# Follow the prompts:
# - Set up and deploy? Y
# - Which scope? (select your account)
# - Link to existing project? N
# - Project name: job-scraper-web
# - In which directory is your code located? ./
```

## Environment Variables

Set these environment variables in your Vercel project settings:

### Required Variables

```bash
# Secret key for Flask sessions
SECRET_KEY=your-secret-key-here

# Database URL (see Database Setup section)
DATABASE_URL=/tmp/jobs.db
```

### Optional Variables

```bash
# Flask environment
FLASK_ENV=production

# Enable debug mode (set to "false" for production)
DEBUG=false
```

## Database Setup

Since Vercel is serverless, you have several options for database persistence:

### Option 1: Upload SQLite Database (Simple)

1. **Upload your `jobs.db` file** to your repository
2. **Set environment variable**: `DATABASE_URL=./jobs.db`
3. **Note**: Database will be read-only in serverless environment

### Option 2: External Database (Recommended for Production)

For a production deployment, consider using:

- **PostgreSQL**: Vercel Postgres, Neon, or Supabase
- **MySQL**: PlanetScale or Railway
- **MongoDB**: MongoDB Atlas

You'll need to modify the `VercelDatabaseManager` class in `api/index.py` to use your chosen database.

### Option 3: Vercel Postgres (Recommended)

```bash
# Add Vercel Postgres to your project
vercel postgres create

# This will provide you with a DATABASE_URL
# Set it in your environment variables
```

## Deployment Configuration Files

### vercel.json

```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/static/(.*)",
      "dest": "/static/$1"
    },
    {
      "src": "/(.*)",
      "dest": "/api/index.py"
    }
  ],
  "env": {
    "FLASK_APP": "api/index.py"
  },
  "functions": {
    "api/index.py": {
      "maxDuration": 30
    }
  }
}
```

### requirements-vercel.txt

Minimal dependencies for the web interface:

```
flask>=2.3.0
werkzeug>=2.3.0
python-dotenv>=1.0.0
```

## Post-Deployment

After deployment:

1. **Check Health Endpoint**: Visit `https://your-app.vercel.app/api/health`
2. **Test Web Interface**: Visit `https://your-app.vercel.app/`
3. **Monitor Logs**: Use Vercel dashboard or CLI: `vercel logs`

## Limitations and Considerations

### Serverless Limitations

- **Cold Starts**: First request may be slower
- **Execution Time**: Maximum 30 seconds per request
- **Memory**: Limited memory per function
- **File System**: Read-only, except `/tmp` directory

### Database Considerations

- **SQLite**: Works but is read-only in serverless environment
- **Connection Pooling**: Not persistent across function invocations
- **Transactions**: Keep them short

### Static Files

- Static files are served directly by Vercel's CDN
- Located in `/static/` directory
- Automatically optimized and cached

## Troubleshooting

### Common Issues

1. **Import Errors**:
   ```bash
   # Check your requirements-vercel.txt file
   # Ensure all dependencies are listed
   ```

2. **Database Connection Issues**:
   ```bash
   # Check DATABASE_URL environment variable
   # Verify database file exists (for SQLite)
   ```

3. **Template Not Found**:
   ```bash
   # Ensure templates/ directory is in repository
   # Check template_folder path in Flask app
   ```

4. **Function Timeout**:
   ```bash
   # Optimize database queries
   # Increase maxDuration in vercel.json (max 60s on Pro plan)
   ```

### Debugging

1. **Check Logs**:
   ```bash
   vercel logs --follow
   ```

2. **Local Testing**:
   ```bash
   cd api
   python index.py
   ```

3. **Health Check**:
   ```bash
   curl https://your-app.vercel.app/api/health
   ```

## Custom Domain (Optional)

To use a custom domain:

1. Go to your project in Vercel dashboard
2. Click "Domains" tab
3. Add your domain
4. Configure DNS as instructed

## Environment-Specific Configurations

### Development
```bash
DEBUG=true
DATABASE_URL=./jobs.db
```

### Production
```bash
DEBUG=false
SECRET_KEY=your-production-secret-key
DATABASE_URL=your-production-database-url
```

## Security Best Practices

1. **Environment Variables**: Never commit secrets to repository
2. **Secret Key**: Use a strong, unique secret key for production
3. **Database**: Use encrypted connections for external databases
4. **HTTPS**: Vercel provides HTTPS by default

## Performance Optimization

1. **Database Queries**: Use indexes and limit result sets
2. **Caching**: Consider adding caching headers
3. **Static Files**: Optimize images and minify CSS/JS
4. **Database Pooling**: Use connection pooling for external databases

## Monitoring and Alerts

1. **Vercel Analytics**: Enable in project settings
2. **Error Tracking**: Consider integrating Sentry
3. **Uptime Monitoring**: Use services like Pingdom or UptimeRobot
4. **Performance**: Monitor function execution times

## Updating the Application

```bash
# Method 1: Git push (automatic deployment)
git add .
git commit -m "Update application"
git push origin main

# Method 2: Vercel CLI
vercel --prod
```

## Support and Resources

- **Vercel Documentation**: [vercel.com/docs](https://vercel.com/docs)
- **Flask Documentation**: [flask.palletsprojects.com](https://flask.palletsprojects.com)
- **Python on Vercel**: [vercel.com/docs/functions/serverless-functions/runtimes/python](https://vercel.com/docs/functions/serverless-functions/runtimes/python)

## Example Production Setup

For a complete production setup, consider this workflow:

1. **Repository**: Store code on GitHub
2. **Database**: Use Vercel Postgres or Supabase
3. **Environment**: Set production environment variables
4. **Domain**: Configure custom domain
5. **Monitoring**: Set up error tracking and uptime monitoring
6. **Backup**: Regular database backups
7. **CI/CD**: Automatic deployments on push to main branch

This setup provides a scalable, maintainable web interface for your job scraper with minimal infrastructure management.