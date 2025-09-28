#!/usr/bin/env python3
"""
Simple startup script for the Job Scraper Web Interface.
This script provides an easy way to start the web server with different configurations.
"""

import argparse
import os
import sys
import webbrowser
from threading import Timer

def main():
    parser = argparse.ArgumentParser(
        description="Start the Job Scraper Web Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_web.py                    # Start on default port 5000
  python run_web.py --port 8080        # Start on port 8080
  python run_web.py --debug            # Start in debug mode
  python run_web.py --host 0.0.0.0     # Allow external connections
  python run_web.py --no-browser       # Don't open browser automatically
        """
    )
    
    parser.add_argument('--host', default='127.0.0.1',
                       help='Host to bind to (default: 127.0.0.1)')
    parser.add_argument('--port', type=int, default=5000,
                       help='Port to run on (default: 5000)')
    parser.add_argument('--debug', action='store_true',
                       help='Run in debug mode')
    parser.add_argument('--no-browser', action='store_true',
                       help='Don\'t open browser automatically')
    parser.add_argument('--public', action='store_true',
                       help='Allow external connections (sets host to 0.0.0.0)')
    
    args = parser.parse_args()
    
    # Set host to 0.0.0.0 if public flag is used
    if args.public:
        args.host = '0.0.0.0'
    
    # Set environment variables
    os.environ['PORT'] = str(args.port)
    os.environ['DEBUG'] = str(args.debug).lower()
    
    # Check if database exists
    db_path = './jobs.db'
    if not os.path.exists(db_path):
        print("Warning: Database file 'jobs.db' not found.")
        print("   The web interface will work but may show no data.")
        print("   Add companies using: python scrape_cli.py add \"Company Name\"")
        print()
    
    # Print startup information
    print("Starting Job Scraper Web Interface...")
    print(f"   Host: {args.host}")
    print(f"   Port: {args.port}")
    print(f"   Debug: {args.debug}")
    
    if args.host == '0.0.0.0':
        print(f"   URL: http://localhost:{args.port}")
        print(f"   External URL: http://YOUR_SERVER_IP:{args.port}")
    else:
        print(f"   URL: http://{args.host}:{args.port}")
    
    print()
    print("Press Ctrl+C to stop the server")
    print("-" * 50)
    
    # Open browser after a short delay (unless disabled)
    if not args.no_browser and args.host in ['127.0.0.1', 'localhost']:
        def open_browser():
            url = f"http://127.0.0.1:{args.port}"
            print(f"Opening browser to {url}")
            webbrowser.open(url)
        
        Timer(1.5, open_browser).start()
    
    try:
        # Import and run the Flask app
        from web_app import app
        app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)
        
    except ImportError as e:
        print(f"Error: Could not import Flask app: {e}")
        print("Make sure you have installed the requirements:")
        print("pip install -r requirements.txt")
        sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n Server stopped by user")
        
    except Exception as e:
        print(f"Error starting server: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()