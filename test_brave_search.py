#!/usr/bin/env python3
"""
Basic test script for Brave Search API.
Shows what our LLM sees from Brave search results.

Usage: python test_brave_search.py "your search query"
"""

import json
import requests
import logging
import sys
from config import Config

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_brave_search(query: str = "Google internship careers"):
    """
    Test Brave Search API and display what the LLM would see.
    
    Args:
        query: Search query to test with
    """
    print(f"\n{'='*60}")
    print(f"TESTING BRAVE SEARCH")
    print(f"{'='*60}")
    print(f"Query: {query}")
    print(f"{'='*60}\n")
    
    # Check if API key exists
    if not Config.BRAVE_API_KEY:
        print("ERROR: BRAVE_API_KEY not found in environment variables")
        print("Please set your Brave Search API key in your .env file")
        return
    
    # Set up the API request
    base_url = "https://api.search.brave.com/res/v1/web/search"
    headers = {
        "Accept": "application/json",
        "X-Subscription-Token": Config.BRAVE_API_KEY
    }
    
    params = {
        "q": query,
        "result_filter": "web",
        "count": 5,  # Limit to 5 results for testing
        "safesearch": "moderate"
    }
    
    try:
        # Make the API request
        print("Making API request to Brave Search...")
        response = requests.get(base_url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        # Parse the response
        data = response.json()
        
        print(f"✓ Request successful! Status code: {response.status_code}")
        print(f"✓ Response size: {len(response.text)} characters\n")
        
        # Display what the LLM sees
        print("RAW JSON STRUCTURE:")
        print("-" * 40)
        print(json.dumps(data, indent=2)[:1000] + "..." if len(json.dumps(data, indent=2)) > 1000 else json.dumps(data, indent=2))
        print()
        
        # Extract and display search results in a formatted way
        if 'web' in data and 'results' in data['web']:
            results = data['web']['results']
            
            print("FORMATTED SEARCH RESULTS (What LLM sees):")
            print("-" * 50)
            
            for i, result in enumerate(results, 1):
                print(f"Result #{i}:")
                print(f"  URL: {result.get('url', 'N/A')}")
                print(f"  Title: {result.get('title', 'N/A')}")
                print(f"  Description: {result.get('description', 'N/A')}")
                
                # Show additional fields if they exist
                if 'meta_url' in result:
                    print(f"  Meta URL: {result['meta_url']['hostname']}")
                
                print()
            
            print(f"Total results returned: {len(results)}")
            
            # Show what would be sent to AI for URL selection
            print("\nAI PROMPT DATA (For URL Selection):")
            print("-" * 40)
            results_text = ""
            for i, result in enumerate(results, 1):
                url = result.get('url', '')
                title = result.get('title', '')
                description = result.get('description', '')
                
                results_text += f"{i}. URL: {url}\n"
                results_text += f"   Title: {title}\n"
                results_text += f"   Description: {description}\n\n"
            
            print(results_text)
            
        else:
            print("No web results found in the response")
            
    except requests.exceptions.RequestException as e:
        print(f"ERROR: API request failed: {str(e)}")
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse JSON response: {str(e)}")
    except Exception as e:
        print(f"ERROR: Unexpected error: {str(e)}")

def main():
    """Main test function that accepts command-line arguments."""
    print("BRAVE SEARCH API TEST SCRIPT")
    print("This script shows what our LLM sees from Brave search results")
    
    # Check if query was provided as command-line argument
    if len(sys.argv) > 1:
        # Use the provided query
        query = " ".join(sys.argv[1:])  # Join all arguments in case query has spaces
        test_brave_search(query)
    else:
        # Default behavior with example queries
        print("\nNo query provided. Running with example queries...")
        print("Usage: python test_brave_search.py \"your search query\"")
        print("\nRunning examples:\n")
        
        test_queries = [
            "Google internship careers",
            "Microsoft student opportunities", 
            "Apple jobs internships",
        ]
        
        for query in test_queries:
            test_brave_search(query)
            print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    main()
