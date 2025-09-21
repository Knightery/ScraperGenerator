#!/usr/bin/env python3
"""
Test script for AI Navigator with LLM-focused retry system
"""

import sys
import os
import logging
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_navigator import AINavigator

def test_ai_navigation(url, company_name=None):
    """Test the new LLM-focused AI navigation system."""
    
    print("🤖 AI Navigator Test (LLM-Focused with Retry)")
    print("=" * 60)
    print(f"Testing URL: {url}")
    if company_name:
        print(f"Company: {company_name}")
    print()
    
    try:
        navigator = AINavigator()
        
        print("🔍 Analyzing job board with retry system...")
        analysis = navigator.analyze_job_board(url)
        
        if "error" in analysis:
            print(f"❌ Analysis failed: {analysis['error']}")
            return False
        
        print("✅ Analysis completed successfully!")
        print()
        
        # Display results
        final_url = analysis.get("final_url", url)
        if final_url != url:
            print(f"🎯 AI navigated to: {final_url}")
        else:
            print("🎯 AI stayed on original page")
        
        print("\n📊 Analysis Results:")
        selectors = [
            "job_container_selector", "title_selector", "url_selector",
            "description_selector", "location_selector", "pagination_selector"
        ]
        
        for selector in selectors:
            value = analysis.get(selector, "Not found")
            print(f"  {selector}: {value}")
        
        print(f"\n  has_dynamic_loading: {analysis.get('has_dynamic_loading', False)}")
        
        # Show LLM evaluation results if available
        if analysis.get('issues'):
            print(f"\n⚠️  Issues found: {analysis['issues']}")
        if analysis.get('suggestions'):
            print(f"💡 Suggestions: {analysis['suggestions']}")
        
        # Generate files
        if not company_name:
            company_name = "TestCompany"
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print("\n🔧 Generating scraper script...")
        scraper_script = navigator.generate_scraper_script(company_name, url, analysis)
        script_filename = f"test_scraper_{company_name.lower().replace(' ', '_')}_{timestamp}.py"
        
        with open(script_filename, 'w', encoding='utf-8') as f:
            f.write(scraper_script)
        
        print(f"✅ Scraper script saved to: {script_filename}")
        print(f"\nRun with: python {script_filename}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {str(e)}")
        return False

def main():
    """Main function."""
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) < 2:
        print("Usage: python test_ai_navigator.py <URL> [company_name]")
        print()
        print("Examples:")
        print("  python test_ai_navigator.py https://careers.google.com/")
        print("  python test_ai_navigator.py https://careers.microsoft.com/ Microsoft")
        print()
        print("Tests the LLM-focused retry system for job board analysis.")
        sys.exit(1)
    
    url = sys.argv[1]
    company_name = sys.argv[2] if len(sys.argv) > 2 else None
    
    if not url.startswith(('http://', 'https://')):
        print("❌ Error: URL must start with http:// or https://")
        sys.exit(1)
    
    success = test_ai_navigation(url, company_name)
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()