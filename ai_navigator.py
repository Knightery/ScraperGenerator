import json
import logging
import time
from typing import Dict, List, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from google import genai
import os
from datetime import datetime
from dotenv import load_dotenv
from pydantic import BaseModel
from config import Config
from html_cleaning_utils import clean_html_content_comprehensive
from playwright.sync_api import sync_playwright
from playwright_scraper import PlaywrightScraperSync

load_dotenv()

gemini_model = "gemini-2.5-flash"

class JobBoardAnalysis(BaseModel):
    job_container_selector: str
    title_selector: str
    url_selector: str
    description_selector: str
    location_selector: str
    pagination_selector: str
    has_dynamic_loading: bool

class AINavigator:
    """
    AI-powered website navigation and scraper generation using Gemini.
    
    Uses its own browser session for navigation, content fetching, and search interactions.
    Uses PlaywrightScraper for validation and testing of generated scraper configurations.
    """
    
    def __init__(self, search_engine=None, company_name=None):
        self.logger = logging.getLogger(__name__)
        self.client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
        self._page_cache = {}  # Cache for cleaned page content
        self._content_cache = {}  # Cache for raw page content
        self._navigation_history = []  # Track navigation history for back functionality
        self._rejected_pages = {}  # Track pages that were rejected and why
        # Persistent browser session for navigation and content fetching
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None  # Single persistent page instance
        # Search engine context for going back to search results
        self._search_engine = search_engine
        self._company_name = company_name
    
    def __enter__(self):
        """Context manager entry."""
        self._start_browser()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self._close_browser()
        return False
    
    def _llm_query(self, prompt: str, json_response: bool = False) -> str:
        """Shared LLM query helper."""
        config = {"response_mime_type": "application/json"} if json_response else {}
        response = self.client.models.generate_content(
            model=gemini_model, contents=prompt, config=config
        )
        return response.text.strip()
    
    def _start_browser(self):
        """Start persistent browser session with single page instance."""
        if not self._browser:
            self.logger.info("Starting persistent browser session...")
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.firefox.launch(
                headless=True,  # Set to True for production
                firefox_user_prefs={
                    "javascript.enabled": True,
                    "dom.webdriver.enabled": False,
                    "useAutomationExtension": False,
                    "general.useragent.override": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
                }
            )
            self._context = self._browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
                # Modern anti-detection settings
                extra_http_headers={
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
                }
            )
            
            # Create single persistent page instance
            self._page = self._context.new_page()
            
            # Enhanced anti-detection setup
            self._page.add_init_script("""
                // Remove webdriver property
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                
                // Remove automation indicators
                window.chrome = {runtime: {}};
                Object.defineProperty(navigator, 'permissions', {
                    get: () => undefined
                });
            """)
            
            self.logger.info("Persistent browser session initialized")
        else:
            self.logger.info("Reusing existing persistent browser session")
    
    def _close_browser(self):
        """Close browser session and clean up resources."""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._playwright = self._browser = self._context = self._page = None
    
    def _export_cleaned_html(self, cleaned_html: str, url: str):
        """Export cleaned HTML to file for debugging."""
        import re
        import os
        
        # Create safe filename from URL
        safe_filename = re.sub(r'[^\w\-_.]', '_', url.replace('https://', '').replace('http://', ''))
        safe_filename = re.sub(r'_+', '_', safe_filename)  # Collapse multiple underscores
        safe_filename = safe_filename.strip('_')  # Remove leading/trailing underscores
        
        # Create debug directory
        debug_dir = "debug_html"
        os.makedirs(debug_dir, exist_ok=True)
        
        # Export cleaned HTML
        filename = f"{debug_dir}/{safe_filename}_cleaned.html"
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(cleaned_html)
            self.logger.info(f"Exported cleaned HTML to: {filename}")
        except Exception as e:
            self.logger.warning(f"Failed to export HTML: {str(e)}")
    
    def analyze_job_board(self, url: str) -> Dict:
        """Analyze a job board website and identify scraping targets with retry mechanism."""
        self.logger.info(f"Analyzing job board: {url}")
        
        try:
            max_attempts = Config.AI_RETRY_ATTEMPTS
            
            # Do navigation and page fetching only once
            self.logger.info("Initial navigation and page fetching...")
            internship_url = self._find_internship_page(url)
            if not internship_url:
                return {"error": "Could not find internship page"}
            
            page_content = self._get_page_content(internship_url)
            if not page_content:
                return {"error": "Could not access internship page content"}
            
            # Get cleaned HTML for analysis
            content_data = self._extract_clean_content_and_links(page_content, internship_url)
            html_structure = content_data['cleaned_html']
            
            # Check for search bar and determine if search is needed for future scraping
            search_analysis = self._handle_search_bar_interaction(internship_url, page_content, content_data)
            search_info = {'search_required': False, 'search_input_selector': '', 'search_submit_selector': ''}
            
            if search_analysis and search_analysis.get('search_performed'):
                # Search was successfully performed - this means future scraping needs search
                search_info['search_required'] = True
                search_info['search_input_selector'] = search_analysis.get('search_input_selector', '')
                search_info['search_submit_selector'] = search_analysis.get('search_submit_selector', '')
                
                if search_analysis.get('new_url'):
                    # URL actually changed after search, update our target URL
                    internship_url = search_analysis['new_url']
                    self.logger.info(f"URL changed after search interaction: {internship_url}")
                else:
                    # Search was performed but URL didn't change - content was updated in place
                    self.logger.info("Search performed successfully, content updated in place")
                
                # Use the fresh content from search result (regardless of URL change)
                updated_content = search_analysis.get('updated_content')
                if updated_content:
                    self.logger.info("Using fresh content from search results")
                    content_data = self._extract_clean_content_and_links(updated_content, internship_url)
                    html_structure = content_data['cleaned_html']
                else:
                    self.logger.warning("No updated content returned from search, fetching fresh content")
                    # Fallback: clear cache and get fresh content
                    if internship_url in self._content_cache:
                        del self._content_cache[internship_url]
                    new_page_content = self._get_page_content(internship_url)
                    if new_page_content:
                        content_data = self._extract_clean_content_and_links(new_page_content, internship_url)
                        html_structure = content_data['cleaned_html']
            
            # Retry loop for AI analysis and validation only
            previous_feedback = None
            
            for attempt in range(1, max_attempts + 1):
                self.logger.info(f"Analysis attempt {attempt}/{max_attempts}")
                
                try:
                    # Generate analysis with previous feedback if available
                    analysis = self._analyze_with_ai_with_feedback(internship_url, html_structure, previous_feedback)
                    if "error" in analysis:
                        self.logger.warning(f"Attempt {attempt}: AI analysis failed: {analysis['error']}")
                        if attempt < max_attempts:
                            self._wait_before_retry(attempt)
                            continue
                        return analysis
                    
                    # Add search information to analysis (search fields handled separately from AI analysis)
                    self.logger.info(f"Applying search info: {search_info}")
                    analysis.update(search_info)
                    analysis["final_url"] = internship_url
                    self.logger.info(f"Final analysis includes search_required: {analysis.get('search_required', 'MISSING')}")
                    
                    # Validate the generated config
                    validation_result = self._validate_complete_config(analysis, internship_url, html_structure)
                    
                    if validation_result["success"]:
                        self.logger.info(f"Analysis successful on attempt {attempt}")
                        analysis.update(validation_result)
                        return analysis
                    else:
                        # Prepare feedback for next attempt
                        previous_feedback = {
                            "previous_analysis": analysis,
                            "validation_issues": validation_result.get('issues', []),
                            "suggestions": validation_result.get('suggestions', []),
                            "attempt": attempt
                        }
                        
                        error_msg = validation_result.get('error', f"LLM recommended retry. Issues: {validation_result.get('issues', [])}")
                        self.logger.warning(f"Attempt {attempt}: Config validation failed: {error_msg}")
                        
                        if attempt < max_attempts:
                            self._wait_before_retry(attempt)
                            continue
                        return {"error": f"Config validation failed after all retry attempts: {error_msg}"}
                        
                except Exception as e:
                    self.logger.error(f"Attempt {attempt}: Unexpected error during analysis: {str(e)}")
                    if attempt < max_attempts:
                        self._wait_before_retry(attempt)
                        continue
                    return {"error": f"Analysis failed after all retry attempts: {str(e)}"}
            
            return {"error": "Analysis failed after all retry attempts"}
        finally:
            # Always close browser when analysis is complete
            self._close_browser()
    
    def _find_internship_page(self, initial_url: str) -> Optional[str]:
        """Navigate from a general careers page to the specific internship page."""
        self.logger.info(f"Starting navigation from: {initial_url}")
        
        # Initialize navigation history with the starting URL
        self._navigation_history = [initial_url]
        
        page_content = self._get_page_content(initial_url)
        if not page_content:
            self.logger.warning("Could not get page content")
            return initial_url
        
        self.logger.info("Got page content, analyzing with AI for navigation...")
        
        # Have AI decide what to click
        next_url = self._ai_navigate(initial_url, page_content)
        
        # Check if search engine provided a new URL
        if next_url and next_url.startswith("SEARCH_ENGINE:"):
            search_engine_url = next_url[14:]  # Remove "SEARCH_ENGINE:" prefix
            self.logger.info(f"Search engine provided new URL, restarting navigation: {search_engine_url}")
            
            # Reset navigation state and restart with new URL
            self._navigation_history = []
            self._rejected_pages = {}
            self._page_cache = {}
            self._content_cache = {}
            
            # Restart navigation with the new URL
            return self._find_internship_page(search_engine_url)
        
        if next_url and next_url != initial_url:
            self.logger.info(f"AI decided to navigate to: {next_url}")
            # Add to navigation history
            self._navigation_history.append(next_url)
            
            # Check if we need to navigate further
            new_page_content = self._get_page_content(next_url)
            if new_page_content:
                self.logger.info("Got content from new page, checking if we need to navigate further...")
                final_url = self._ai_evaluate_and_navigate(next_url, new_page_content)
                if final_url and final_url != next_url:
                    # Add final URL to history if it's different
                    self._navigation_history.append(final_url)
                    self.logger.info(f"Final navigation destination: {final_url}")
                    return final_url
            return next_url
        else:
            self.logger.info("AI decided to stay on the original page - skipping re-render")
        
        return initial_url
    
    def _ai_evaluate_and_navigate(self, current_url: str, page_content: str) -> Optional[str]:
        """Evaluate if current page has good internship listings or navigate further."""
        next_url = self._ai_navigate(current_url, page_content)
        
        # Check if search engine provided a new URL
        if next_url and next_url.startswith("SEARCH_ENGINE:"):
            search_engine_url = next_url[14:]  # Remove "SEARCH_ENGINE:" prefix
            self.logger.info(f"Search engine provided new URL during navigation: {search_engine_url}")
            
            # Reset navigation state and restart with new URL
            self._navigation_history = []
            self._rejected_pages = {}
            self._page_cache = {}
            self._content_cache = {}
            
            # Restart navigation with the new URL
            return self._find_internship_page(search_engine_url)
        
        # If AI went back to a previous page, continue navigation from there
        if next_url and next_url != current_url and next_url in self._navigation_history:
            self.logger.info(f"Continuing navigation from previous page: {next_url}")
            back_page_content = self._get_page_content(next_url)
            if back_page_content:
                return self._ai_evaluate_and_navigate(next_url, back_page_content)
        
        # If AI decided to navigate to a different URL (forward navigation), add it to history
        if next_url and next_url != current_url and next_url not in self._navigation_history:
            self._navigation_history.append(next_url)
            self.logger.info(f"Added to navigation history: {next_url}")
        
        return next_url
    
    def _extract_clean_content_and_links(self, page_content: str, base_url: str) -> Dict:
        """Extract clean visible text and links from page content by removing irrelevant sections."""
        # Check cache first
        cache_key = f"{base_url}_{len(page_content)}"
        if cache_key in self._page_cache:
            self.logger.info(f"Using cached cleaned content for {base_url}")
            return self._page_cache[cache_key]
        
        self.logger.info(f"Cleaning content by removing irrelevant sections (original size: {len(page_content):,} chars)")
        
        # Use comprehensive HTML cleaning function
        cleaned_html_str = clean_html_content_comprehensive(page_content, self.logger)
        
        # Safety check for None return
        if cleaned_html_str is None:
            self.logger.warning("HTML cleaning returned None, using original content")
            cleaned_html_str = page_content
        
        # Export cleaned HTML for debugging
        self._export_cleaned_html(cleaned_html_str, base_url)
        
        # Extract visible text from cleaned content
        cleaned_soup = BeautifulSoup(cleaned_html_str, 'html.parser')
        visible_text = cleaned_soup.get_text(separator=' ', strip=True)
        visible_text = ' '.join(visible_text.split())  # Clean whitespace
                
        # Extract links from cleaned content
        links = []
        for link in cleaned_soup.find_all('a', href=True):
            href = link.get('href', '').strip()
            if href and not href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                absolute_url = urljoin(base_url, href)
                link_text = link.get_text(strip=True)
                if link_text:  # Only include links with text
                    links.append({
                        'text': link_text,
                        'url': absolute_url
                    })
        
        # Extract iframe src links
        for iframe in cleaned_soup.find_all('iframe', src=True):
            src = iframe.get('src', '').strip()
            if src and not src.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                absolute_url = urljoin(base_url, src)
                # Use iframe attributes or surrounding text as link text
                iframe_text = iframe.get('title', '') or iframe.get('name', '') or iframe.get('id', '') or 'iframe'
                if iframe_text:
                    links.append({
                        'text': iframe_text,
                        'url': absolute_url
                    })
        
        result = {
            'visible_text': visible_text,
            'links': links,
            'cleaned_html': cleaned_html_str
        }
        
        # Cache the result
        self._page_cache[cache_key] = result
        
        return result
    
    def _ai_navigate(self, current_url: str, page_content: str) -> Optional[str]:
        """AI navigation method to analyze page and decide whether to stay, navigate, or go back."""
        content_data = self._extract_clean_content_and_links(page_content, current_url)
        visible_text = content_data['visible_text']
        links = content_data['links']
        
        if not links:
            self.logger.info("No links found for navigation")
            return current_url
        
        # Filter links containing job-related keywords first
        job_keywords = ['jobs', 'intern', 'oppor', 'career']  # oppor catches opportunity/opportunities
        filtered_links = [link for link in links 
                         if any(keyword in link['text'].lower() or keyword in link['url'].lower() 
                               for keyword in job_keywords)]
        
        # Use filtered links if found, otherwise use all links
        relevant_links = filtered_links if filtered_links else links
        self.logger.info(f"Using {'filtered' if filtered_links else 'all'} links: {len(relevant_links)}/{len(links)}")
        
        links_text = "\n".join(f"{i}. \"{link['text']}\" -> {link['url']}" 
                              for i, link in enumerate(relevant_links, 1))
        
        # Always allow BACK navigation
        can_go_back = len(self._navigation_history) > 1
        back_option = f"\nBACK: Go back to previous page ({self._navigation_history[-2] if can_go_back else 'search for different website'})"
        
        # Build feedback about previously rejected pages
        rejected_feedback = ""
        if self._rejected_pages:
            rejected_info = []
            for url, reason in self._rejected_pages.items():
                rejected_info.append(f"- {url}: {reason}")
            rejected_feedback = f"\n\nPREVIOUSLY REJECTED PAGES (avoid these):\n" + "\n".join(rejected_info)
        
        prompt = f"""TASK: Navigate to find internship job listings page.

RETURN LOGIC:
- "STAY" if you see 3+ internship job titles with apply buttons
- "BACK" if no internships found or error messages
- NUMBER (1-N) to click link for internship listings
- "0" if no relevant links

INTERNSHIP INDICATORS: "Intern", "Summer", "Co-op", "Graduate Program", "Entry Level"
AVOID: "VP", "Director", "Senior", "Manager" roles

Context: Website navigation to find scrapable internship listings.

Analyze this careers page: {current_url}

PAGE CONTENT:
{visible_text[:5000]}

AVAILABLE LINKS TO CLICK:
{links_text}{back_option}{rejected_feedback}

Does this page show specific internship job listings, or do I need to click a link to find them, or should I go back?

Response (ONLY return 'STAY', 'BACK', a number 1-N, or '0'):"""
        
        for attempt in range(3):
            response_text = self._llm_query(prompt).upper().strip()
            self.logger.info(f"AI navigation decision: {response_text}")
            
            try:
                if response_text == "STAY":
                    return current_url
                elif response_text == "BACK":
                    # Capture why this page was rejected before going back
                    rejection_reason = self._get_rejection_reason(current_url, visible_text)
                    self._rejected_pages[current_url] = rejection_reason
                    
                    if can_go_back:
                        # Use proper browser back navigation instead of URL navigation
                        self.logger.info(f"AI decided to go BACK using browser back navigation")
                        
                        # Use browser's back functionality
                        self._page.go_back(wait_until='networkidle')
                        
                        # Update navigation history to reflect the back navigation
                        self._navigation_history.pop()  # Remove current URL
                        back_url = self._page.url
                        
                        self.logger.info(f"Browser navigated back to: {back_url}")
                        
                        # Update content cache with the back page content
                        back_content = self._page.content()
                        self._content_cache[back_url] = back_content
                        
                        return back_url
                    else:
                        # No history available - this means we're on the first page, show search results
                        self.logger.info(f"AI wanted to go BACK but no history available. Showing search results.")
                        
                        if self._search_engine and self._company_name:
                            new_url = self._search_engine.search_company_jobs_with_feedback(self._company_name, [{"url": current_url, "reason": rejection_reason}])
                            if new_url:
                                self.logger.info(f"Search engine provided new URL: {new_url}")
                                # Return special marker to indicate this is a search engine URL that needs fresh navigation
                                return f"SEARCH_ENGINE:{new_url}"
                        
                        return current_url
                else:
                    selection = int(response_text)
                    if 1 <= selection <= len(relevant_links):
                        selected_link = relevant_links[selection - 1]
                        selected_url = selected_link['url']
                        self.logger.info(f"AI selected link {selection}: '{selected_link['text']}' -> {selected_url}")
                        return selected_url
                    elif selection == 0:
                        self.logger.info("AI selected 0 - no relevant links")
                        return current_url
                    else:
                        raise ValueError(f"Invalid selection: {selection}")
            except (ValueError, TypeError) as e:
                self.logger.warning(f"Failed to parse AI response '{response_text}' (attempt {attempt + 1}/3): {e}")
                if attempt == 2:  # Last attempt
                    return current_url
        
        return current_url
    
    def _get_rejection_reason(self, url: str, visible_text: str) -> str:
        """Get a brief reason why the current page was rejected."""
        prompt = f"""TASK: Explain why this page lacks internship listings.

URL: {url}
CONTENT: {visible_text[:3000]}

Return 1-2 sentences explaining the issue:"""

        reason = self._llm_query(prompt).strip()
        return reason if reason else "Page does not contain internship job listings"
    
    def _handle_search_bar_interaction(self, url: str, page_content: str, content_data: Dict = None) -> Optional[Dict]:
        """Handle search bar detection and interaction if needed."""
        search_analysis = self._llm_analyze_search_need(url, page_content, content_data)
        if not search_analysis or not search_analysis.get('search_required'):
            return None
        return self._perform_search(url, search_analysis)
    
    def _llm_analyze_search_need(self, url: str, page_content: str, content_data: Dict = None) -> Optional[Dict]:
        """Use LLM to analyze if we need to search and identify search elements."""
        if content_data is None:
            content_data = self._extract_clean_content_and_links(page_content, url)
        visible_text = content_data['visible_text'][:8000]
        html_structure = content_data['cleaned_html'][:100000]
        
        prompt = f"""TASK: Determine if search is needed to filter for internships only.

REQUIRED: If TRUE, provide EXACT CSS selectors from HTML below.

URL: {url}
CONTENT: {visible_text}
HTML: {html_structure}

Return JSON:
{{
  "search_required": true/false,
  "search_query": "internship",
  "search_input_selector": "exact CSS selector",
  "search_submit_selector": "exact CSS selector or empty if none, none may allow for enter to submit",
  "reasoning": "one sentence"
}}

Context: Search interaction for internship-only scraping."""

        result = json.loads(self._llm_query(prompt, json_response=True))
        self.logger.info(f"LLM search analysis: {result.get('reasoning', 'No reasoning provided')}")
        return result
    
    def _perform_search(self, url: str, search_analysis: Dict) -> Optional[Dict]:
        """Perform search interaction."""
        search_query = search_analysis.get('search_query', 'intern')
        input_selector = search_analysis.get('search_input_selector', '')
        submit_selector = search_analysis.get('search_submit_selector', '')
        
        if not input_selector:
            return None
            
        # Navigate to page if not already there
        if self._page is None or self._page.url != url:
            self._get_page_content(url)
            
        original_url = self._page.url
        
        # Fill and submit search
        self._page.fill(input_selector, search_query)
        
        if submit_selector:
            self._page.click(submit_selector)
        else:
            self._page.press(input_selector, 'Enter')
            
        self._page.wait_for_load_state('networkidle')
        
        # Get results
        current_url = self._page.url
        content = self._page.content()
        
        if self._llm_verify_search_success(content, current_url):
            self._content_cache[current_url] = content
            
            result = {
                'search_performed': True, 
                'search_input_selector': input_selector,
                'search_submit_selector': submit_selector,
                'updated_content': content
            }
            
            if current_url != original_url:
                result['new_url'] = current_url
            
            return result
        
        return None
       
    def _llm_verify_search_success(self, page_content: str, current_url: str, content_data: Dict = None) -> bool:
        """Ask LLM if we successfully reached job listings after search."""
        if content_data is None:
            content_data = self._extract_clean_content_and_links(page_content, current_url)
        visible_text = content_data['visible_text'][:5000]
        
        prompt = f"""TASK: Verify search loaded job listings.

URL: {current_url}
CONTENT: {visible_text}

Return "YES" if job titles + apply buttons visible.
Return "NO" if only search forms or no jobs.

Context: Post-search validation."""

        response = self._llm_query(prompt).upper().strip()
        success = response == "YES"
        self.logger.info(f"LLM search verification: {response} -> {success}")
        return success
    
    def _get_page_content(self, url: str) -> Optional[str]:
        """Get page content with caching."""
        if url in self._content_cache:
            return self._content_cache[url]
            
        self._start_browser()
        self._page.goto(url, wait_until='networkidle')
        content = self._page.content()
        self._content_cache[url] = content
        return content
    
    def _generate_analysis_system_prompt(self, is_retry: bool = False) -> str:
        """Generate system prompt for AI analysis."""
        if is_retry:
            return """You are an expert web scraper analyzer. You previously analyzed this page but the selectors didn't work well. 

Based on the feedback, analyze the HTML structure again and provide BETTER CSS selectors for job listings.

You MUST return ONLY a valid JSON object with these exact keys:
{
  "job_container_selector": "CSS selector for individual job listings (e.g., \".cmp-jobcard\")",
  "title_selector": "CSS selector for job titles relative to container (e.g., \".cmp-jobcard__title\")",
  "url_selector": "CSS selector for job links relative to container (e.g., \"a\")",
  "description_selector": "CSS selector for descriptions if available (e.g., \".description_text\")",
  "location_selector": "CSS selector for locations if available (e.g., \".cmp-jobcard__location\")",
  "pagination_selector": "CSS selector for pagination/next page (e.g., \".next\")",
  "has_dynamic_loading": true/false (true if the page has dynamic loading, false if it does not)
}

CRITICAL SELECTOR REQUIREMENTS:
- Return ONLY the JSON object, no other text
- Use actual CSS selectors from the HTML structure
- Learn from the previous attempt's issues
- Be more specific/different than the previous selectors that failed
- ONLY use CSS2/CSS3 selectors - NO CSS4 selectors like :has(), :contains(), :matches()
- Use basic selectors: class (.class), id (#id), attribute ([attr=\"value\"]), descendant (div span), child (div > span)
- If filtering by text content is needed, select the parent container and let the scraper filter by text"""
        else:
            return """TASK: Generate CSS selectors for job listing containers.

FOCUS: Find repeating patterns for individual job cards/items.
GOAL: Scrape ALL job listings (internship filtering happens later).

Return JSON with exact keys:
{
  "job_container_selector": "CSS selector for job containers",
  "title_selector": "CSS selector for titles relative to container", 
  "url_selector": "CSS selector for links relative to container",
  "description_selector": "CSS selector for descriptions (or empty)",
  "location_selector": "CSS selector for locations (or empty)",
  "pagination_selector": "CSS selector for next page (or empty)",
  "has_dynamic_loading": true/false
}

CONSTRAINTS:
- Use ONLY CSS2/CSS3 selectors
- NO CSS4 selectors like :has(), :contains()
- Use actual selectors from HTML, not examples
- Return ONLY JSON, no other text

Context: CSS selector generation for job scraping."""
    
    def _generate_analysis_user_prompt(self, url: str, html_structure: str, previous_feedback: Optional[Dict] = None) -> str:
        """Generate user prompt for AI analysis."""
        if previous_feedback:
            return f"""RETRY ANALYSIS - Previous attempt failed.

URL: {url}

PREVIOUS ANALYSIS THAT FAILED:
{json.dumps(previous_feedback['previous_analysis'], indent=2)}

ISSUES FOUND:
{previous_feedback['validation_issues']}

SUGGESTIONS:
{previous_feedback['suggestions']}

HTML STRUCTURE:
{html_structure}

Based on this feedback, provide BETTER CSS selectors that will actually work for scraping internship job listings."""
        else:
            return f"""Analyze this internship job board page:

URL: {url}

HTML STRUCTURE:
{html_structure}

Identify specific CSS selectors for scraping internship job listings. Look for repeating HTML patterns that contain job titles, locations, and apply links."""
    
    def _process_analysis_response(self, response) -> Dict:
        """Process Gemini API response and convert to dict format."""
        self.logger.info(f"LLM Raw Response: {response.text}")
        
        # Use the parsed response directly
        analysis_obj: JobBoardAnalysis = response.parsed
        self.logger.info(f"Successfully parsed structured response: {analysis_obj}")
        
        # Convert to dict for compatibility with existing code
        return {
            "job_container_selector": analysis_obj.job_container_selector,
            "title_selector": analysis_obj.title_selector,
            "url_selector": analysis_obj.url_selector,
            "description_selector": analysis_obj.description_selector,
            "location_selector": analysis_obj.location_selector,
            "pagination_selector": analysis_obj.pagination_selector,
            "has_dynamic_loading": analysis_obj.has_dynamic_loading
        }
    
    def _analyze_with_ai(self, url: str, html_structure: str, previous_feedback: Optional[Dict] = None) -> Dict:
        """Unified AI analysis method that handles both initial analysis and retry scenarios with feedback."""
        # Truncate HTML to manageable size
        html_structure = html_structure[:500000]
        
        # Determine if this is a retry attempt
        is_retry = previous_feedback is not None
        
        if is_retry:
            self.logger.info(f"Re-analyzing with feedback from attempt {previous_feedback['attempt']}")
        
        # Generate prompts based on scenario
        system_prompt = self._generate_analysis_system_prompt(is_retry)
        user_prompt = self._generate_analysis_user_prompt(url, html_structure, previous_feedback)
        combined_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        # Make API call with structured response schema
        try:
            response = self.client.models.generate_content(
                model=gemini_model,
                contents=combined_prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": JobBoardAnalysis,
                }
            )
            
            # Process and return response
            return self._process_analysis_response(response)
        except Exception as e:
            self.logger.error(f"AI analysis failed: {str(e)}")
            return {"error": f"AI analysis failed: {str(e)}"}
    

    
    def _wait_before_retry(self, attempt: int):
        """Wait with exponential backoff before retry."""
        wait_time = min(2 ** attempt, 30)  # Cap at 30 seconds
        self.logger.info(f"Waiting {wait_time} seconds before retry...")
        time.sleep(wait_time)
    
    def _analyze_with_ai_with_feedback(self, url: str, html_structure: str, previous_feedback: Optional[Dict]) -> Dict:
        """AI analysis with feedback from previous attempts."""
        # The unified _analyze_with_ai method now handles both scenarios
        return self._analyze_with_ai(url, html_structure, previous_feedback)
    
    def _validate_complete_config(self, analysis: Dict, url: str, html_structure: str) -> Dict:
        """
        Use PlaywrightScraper to validate the configuration.
        
        This delegates to PlaywrightScraper for consistent validation behavior,
        ensuring the same scraping logic is used for both validation and production.
        """
        self.logger.info("Starting PlaywrightScraper-based config validation...")
        
        try:
            # Run PlaywrightScraper in a separate thread to avoid event loop conflicts
            import concurrent.futures
            
            def run_playwright_validation():
                # Create a PlaywrightScraper instance for testing
                playwright_scraper = PlaywrightScraperSync(use_database=False)
                
                # Test selectors using PlaywrightScraper's test_selectors method
                selectors_to_test = {
                    'job_container_selector': analysis.get('job_container_selector', ''),
                    'title_selector': analysis.get('title_selector', ''),
                    'url_selector': analysis.get('url_selector', ''),
                    'description_selector': analysis.get('description_selector', ''),
                    'location_selector': analysis.get('location_selector', ''),
                    'pagination_selector': analysis.get('pagination_selector', '')
                }
                
                # Remove empty selectors
                selectors_to_test = {k: v for k, v in selectors_to_test.items() if v}
                
                selector_results = playwright_scraper.test_selectors(url, selectors_to_test)
                
                # Create a test scraper config to extract sample jobs
                # Note: analysis contains CSS selectors from AI, search fields were added separately
                test_config = {
                    'company_name': analysis.get('company_name', 'Test Company'),
                    'job_container_selector': analysis.get('job_container_selector', ''),
                    'title_selector': analysis.get('title_selector', ''),
                    'url_selector': analysis.get('url_selector', ''),
                    'description_selector': analysis.get('description_selector', ''),
                    'location_selector': analysis.get('location_selector', ''),
                    'pagination_selector': analysis.get('pagination_selector', ''),
                    'search_required': analysis.get('search_required', False),  # Added by search detection, not AI
                    'search_input_selector': analysis.get('search_input_selector', ''),  # Added by search detection, not AI
                    'search_submit_selector': analysis.get('search_submit_selector', ''),  # Added by search detection, not AI
                    'max_pages': 1  # Only test first page for validation
                }
                
                # DEBUG: Print the full test config including search fields
                print(f"\n=== DEBUG: TEST CONFIG ===")
                print(f"URL: {url}")
                print(f"Config used for validation:")
                for key, value in test_config.items():
                    print(f"  {key}: {repr(value)}")
                print(f"========================\n")
                
                # Extract sample jobs using PlaywrightScraper
                jobs, _ = playwright_scraper.scrape_jobs(url, test_config)
                
                return selector_results, jobs
            
            # Run in thread to avoid asyncio event loop conflict
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_playwright_validation)
                selector_results, jobs = future.result(timeout=120)  # 2 minute timeout
            
            self.logger.info(f"PlaywrightScraper validation completed successfully")
            self.logger.info(f"PlaywrightScraper extracted {len(jobs)} sample jobs for validation")
            
            # Create pagination test results based on selector test
            pagination_test = {}
            if analysis.get('pagination_selector'):
                pagination_results = selector_results.get('results', {}).get('pagination_selector', {})
                pagination_test = {
                    "pagination_selector": analysis.get('pagination_selector', ''),
                    "jobs_found": len(jobs),
                    "test_attempted": True,
                    "success": pagination_results.get('success', False),
                    "elements_found": pagination_results.get('elements_found', 0)
                }
            
            # Let LLM evaluate all results
            return self._llm_evaluate_config(analysis, selector_results, jobs, pagination_test, html_structure, url)
            
        except Exception as e:
            self.logger.error(f"PlaywrightScraper validation failed: {str(e)}")
            return {"success": False, "error": f"Validation failed: {str(e)}"}
    
    
    def _llm_evaluate_config(self, analysis: Dict, selector_results: Dict, jobs: List[Dict], pagination_test: Dict, html_structure: str, url: str) -> Dict:
        """Let LLM evaluate the config based on all test results."""
        self.logger.info("LLM evaluating config results...")
        
        # Limit HTML to avoid token limits
        html_structure = html_structure[:200000]
        
        # Prepare job sample
        job_sample = jobs[:3] if jobs else []
        
        system_prompt = """You are evaluating a job scraper configuration for INTERNSHIP positions. Analyze the test results and determine if the config is good or needs improvement. You have been fed the first 3 jobs extracted as a sample.

Return ONLY a valid JSON object with these exact keys:
{
  "success": true/false,
  "issues": ["list of specific issues found"],
  "suggestions": ["list of specific improvements"],
  "retry_recommended": true/false
}

Evaluation guidelines:
- CRITICAL REQUIREMENTS (must work for success):
  * Job container selector finds job elements
  * Title selector extracts job titles successfully
  * URL selector extracts valid job links

- OPTIONAL ELEMENTS (empty/missing is acceptable):
  * Description selector - job pages may not have descriptions on listing pages
  * Location selector - some sites don't show location in listings
  * Requirements selector - often not available on listing pages
  * Pagination selector - only needed if site has multiple pages

- EVALUATION FOCUS:
  * Only flag issues with selectors that are failing to work when they should. 
  * Don't penalize empty optional selectors - they may be intentionally empty
  * Focus on whether the scraper successfully extracts job data (title, URL)
  * Consider the context: listing pages vs detail pages have different available data

Recommend retry if CRITICAL selectors are broken OR if no jobs are being extracted"""

        user_prompt = f"""Evaluate this job scraper configuration:

URL: {url}

ORIGINAL AI ANALYSIS:
{json.dumps(analysis, indent=2)}

SELECTOR TEST RESULTS:
{json.dumps(selector_results, indent=2)}

JOBS EXTRACTED ({len(jobs)} total):
{json.dumps(job_sample, indent=2)}

PAGINATION TEST (if applicable):
{json.dumps(pagination_test, indent=2)}

HTML STRUCTURE (for reference):
{html_structure[:500000]}

Evaluate the configuration quality and recommend if retry is needed."""

        evaluation = json.loads(self._llm_query(f"{system_prompt}\n\n{user_prompt}", json_response=True))
        self.logger.info(f"LLM evaluation: {evaluation.get('success')}")
        return evaluation
    
    def _build_base_config(self, company_name: str, url: str, analysis: Dict) -> Dict:
        """Build base configuration dictionary with common fields."""
        scrape_url = analysis.get("final_url", url)
        
        return {
            'company_name': company_name,
            'scrape_url': scrape_url,
            'job_container_selector': analysis.get('job_container_selector', ''),
            'title_selector': analysis.get('title_selector', ''),
            'url_selector': analysis.get('url_selector', ''),
            'description_selector': analysis.get('description_selector', ''),
            'location_selector': analysis.get('location_selector', ''),
            'requirements_selector': analysis.get('requirements_selector', ''),
            'pagination_selector': analysis.get('pagination_selector', ''),
            'has_dynamic_loading': analysis.get('has_dynamic_loading', False),
            'search_required': analysis.get('search_required', False),
            'search_input_selector': analysis.get('search_input_selector', ''),
            'search_submit_selector': analysis.get('search_submit_selector', ''),
        }
    
    def generate_scraper_config(self, company_name: str, url: str, analysis: Dict) -> Dict:
        """Generate Playwright scraper configuration."""
        config = self._build_base_config(company_name, url, analysis)
        config.update({
            'max_pages': 999,  # Unlimited - will stop automatically based on end conditions
            'created_at': datetime.now().isoformat()
        })
        return config
    
    def generate_scraper_script(self, company_name: str, url: str, analysis: Dict) -> str:
        """Generate a standalone Python script that uses PlaywrightScraper."""
        scrape_url = analysis.get("final_url", url)
        
        # Read the template file
        template_path = os.path.join(os.path.dirname(__file__), 'scraper_template.py')
        with open(template_path, 'r', encoding='utf-8') as f:
            template_content = f.read()
        
        # Prepare template variables using base config
        template_vars = self._build_base_config(company_name, url, analysis)
        
        # Add template-specific fields
        template_vars.update({
            'generated_at': datetime.now().isoformat(),
            'log_filename': f"{company_name.lower().replace(' ', '_')}_scraper.log",
            'has_dynamic_loading': str(template_vars['has_dynamic_loading']),  # Convert to string for template
            'search_required': str(template_vars['search_required']),  # Convert to string for template
            'backup_filename': f"{company_name.lower().replace(' ', '_')}_jobs_{int(datetime.now().timestamp())}.json"
        })
        
        # Fill in the template
        return template_content.format(**template_vars)
