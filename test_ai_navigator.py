#!/usr/bin/env python3
"""
Test script for AI Navigator with LLM-focused retry system
"""

import sys
import os
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_navigator import AINavigator

def test_ai_navigation(url, company_name=None):
    """Test the AI analysis system directly on a URL (skips navigation phase)."""
    
    print("🤖 AI Navigator Test (Direct Analysis - Skip Navigation)")
    print("=" * 60)
    print(f"Testing URL: {url}")
    if company_name:
        print(f"Company: {company_name}")
    print()
    
    try:
        navigator = AINavigator()
        
        print("🔍 Starting direct analysis (skipping navigation)...")
        
        # Skip navigation, go straight to analysis
        navigator._start_browser()
        page_content = navigator._get_page_content(url)
        if not page_content:
            print(f"❌ Could not get page content")
            return False
        
        content_data = navigator._extract_clean_content_and_links(page_content, url)
        html_structure = content_data['cleaned_html']
        
        # Check for search interaction
        print("🔎 Checking for search bar interaction...")
        search_analysis = navigator._handle_search_bar_interaction(url, page_content, content_data)
        search_info = {'search_required': False, 'search_input_selector': '', 'search_submit_selector': '', 'search_query': 'intern'}
        
        if search_analysis and search_analysis.get('search_performed'):
            print(f"✅ Search interaction performed: {search_analysis.get('interaction_mode', 'unknown')} mode")
            search_info = {
                'search_required': True,
                'search_input_selector': search_analysis.get('search_input_selector', ''),
                'search_submit_selector': search_analysis.get('search_submit_selector', ''),
                'search_query': search_analysis.get('search_query', 'intern')
            }
            final_url = navigator._page.url
            updated_content = search_analysis.get('updated_content')
            if updated_content:
                content_data = navigator._extract_clean_content_and_links(updated_content, final_url)
                html_structure = content_data['cleaned_html']
        else:
            print("ℹ️  No search interaction needed")
            final_url = url
        
        # Retry loop for AI analysis and validation
        max_attempts = 3
        previous_feedback = None
        
        for attempt in range(1, max_attempts + 1):
            print(f"\n🔄 Analysis attempt {attempt}/{max_attempts}...")
            
            analysis = navigator._analyze_with_ai(final_url, html_structure, previous_feedback)
            
            if "error" in analysis:
                print(f"❌ Analysis failed: {analysis['error']}")
                return False
            
            # Add search info to analysis
            analysis.update(search_info)
            analysis['final_url'] = final_url
            
            print("✅ AI analysis complete, validating config...")
            validation = navigator._validate_complete_config(analysis, final_url, html_structure)
            
            if validation.get('success'):
                print(f"✅ Validation passed on attempt {attempt}!")
                break
            
            if attempt < max_attempts:
                print(f"⚠️  Validation failed, retrying with feedback...")
                previous_feedback = validation
                navigator._wait_before_retry(attempt)
            else:
                print(f"❌ Validation failed after {max_attempts} attempts")
                return False
        
        navigator._close_browser()
        
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