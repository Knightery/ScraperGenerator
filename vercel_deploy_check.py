#!/usr/bin/env python3
"""
Vercel deployment preparation script.
This script helps prepare the project for Vercel deployment by checking requirements
and providing deployment instructions.
"""

import os
import sys
from pathlib import Path

def check_file_exists(filepath, description):
    """Check if a file exists and print status."""
    if os.path.exists(filepath):
        print(f"✓ {description}: {filepath}")
        return True
    else:
        print(f"✗ {description}: {filepath} (MISSING)")
        return False

def check_vercel_setup():
    """Check if the project is ready for Vercel deployment."""
    print("Checking Vercel deployment readiness...")
    print("=" * 50)
    
    required_files = [
        ("vercel.json", "Vercel configuration"),
        ("api/index.py", "Main API entry point"),
        ("templates", "Template directory"),
        ("static", "Static files directory"),
        ("requirements-vercel.txt", "Vercel requirements"),
        ("README-VERCEL.md", "Deployment guide")
    ]
    
    all_good = True
    
    for filepath, description in required_files:
        if not check_file_exists(filepath, description):
            all_good = False
    
    print("\nOptional files:")
    optional_files = [
        ("jobs.db", "SQLite database"),
        (".env", "Environment variables"),
        ("static/css/style.css", "CSS styles"),
        ("static/js/main.js", "JavaScript files")
    ]
    
    for filepath, description in optional_files:
        check_file_exists(filepath, description)
    
    print("\n" + "=" * 50)
    
    if all_good:
        print("✓ Project is ready for Vercel deployment!")
        print_deployment_instructions()
    else:
        print("✗ Some required files are missing. Please check the setup.")
        return False
    
    return True

def print_deployment_instructions():
    """Print deployment instructions."""
    print("\nDEPLOYMENT INSTRUCTIONS:")
    print("-" * 30)
    
    print("\n1. ENVIRONMENT VARIABLES")
    print("   Set these in your Vercel project settings:")
    print("   • SECRET_KEY=your-secret-key-here")
    print("   • DATABASE_URL=./jobs.db (or your database URL)")
    print("   • DEBUG=false")
    
    print("\n2. DEPLOYMENT OPTIONS")
    print("   Option A - Vercel Dashboard:")
    print("   • Go to vercel.com/dashboard")
    print("   • Import your GitHub repository")
    print("   • Set environment variables")
    print("   • Deploy")
    
    print("   Option B - Vercel CLI:")
    print("   • npm i -g vercel")
    print("   • vercel login")
    print("   • vercel")
    
    print("\n3. POST-DEPLOYMENT")
    print("   • Test: https://your-app.vercel.app/api/health")
    print("   • View app: https://your-app.vercel.app/")
    print("   • Monitor logs: vercel logs")
    
    print(f"\n4. DOCUMENTATION")
    print("   • Read README-VERCEL.md for detailed instructions")
    print("   • Check Vercel docs: vercel.com/docs")

def create_env_example():
    """Create example environment file."""
    env_content = """# Vercel Environment Variables
# Copy these to your Vercel project settings

SECRET_KEY=change-this-to-a-random-secret-key
DATABASE_URL=./jobs.db
DEBUG=false
FLASK_ENV=production
"""
    
    with open('.env.vercel.example', 'w') as f:
        f.write(env_content)
    
    print("✓ Created .env.vercel.example with sample environment variables")

def main():
    """Main function."""
    print("Job Scraper - Vercel Deployment Helper")
    print("=" * 40)
    
    # Check if we're in the right directory
    if not os.path.exists('web_app.py'):
        print("Error: Please run this script from the project root directory")
        print("(The directory containing web_app.py)")
        sys.exit(1)
    
    # Check setup
    if check_vercel_setup():
        create_env_example()
        
        print(f"\n🚀 Ready to deploy!")
        print("Next steps:")
        print("1. Push your code to GitHub")
        print("2. Connect repository to Vercel")
        print("3. Set environment variables")
        print("4. Deploy!")
        
    else:
        print(f"\n❌ Setup incomplete")
        print("Please ensure all required files are present.")

if __name__ == '__main__':
    main()