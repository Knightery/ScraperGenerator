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
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
        self._page_cache = {}  # Cache for cleaned page content
        self._content_cache = {}  # Cache for raw page content
        # Browser session for navigation and content fetching
        self._playwright = None
        self._browser = None
        self._context = None
    
    def _llm_query(self, prompt: str, json_response: bool = False) -> str:
        """Shared LLM query helper."""
        config = {"response_mime_type": "application/json"} if json_response else {}
        response = self.client.models.generate_content(
            model=gemini_model, contents=prompt, config=config
        )
        return response.text.strip()
    
    def _ensure_browser(self):
        """Ensure browser session is running."""
        if not self._browser:
            self.logger.info("Starting new browser session...")
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.firefox.launch(
                headless=True,
                firefox_user_prefs={
                    "javascript.enabled": True,
                    "dom.webdriver.enabled": False,
                    "useAutomationExtension": False,
                    "general.useragent.override": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
                }
            )
            self._context = self._browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
            )
        else:
            self.logger.info("Reusing existing browser session...")
    
    def _new_page(self):
        """Get a new page from the shared browser session."""
        self._ensure_browser()
        page = self._context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        return page
    
    def _close_browser(self):
        """Close the browser session."""
        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._playwright = self._browser = self._context = None
    
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
            
            # Check for search bar and interact if needed
            search_result = self._handle_search_bar_interaction(internship_url, page_content)
            if search_result and search_result.get('new_url'):
                # URL changed after search, update our target URL and get new content
                internship_url = search_result['new_url']
                self.logger.info(f"URL changed after search interaction: {internship_url}")
                
                # Get new page content and clean it
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
                    
                    analysis["final_url"] = internship_url
                    
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
        
        page_content = self._get_page_content(initial_url)
        if not page_content:
            self.logger.warning("Could not get page content")
            return initial_url
        
        self.logger.info("Got page content, analyzing with AI for navigation...")
        
        # Have AI decide what to click
        next_url = self._ai_navigate(initial_url, page_content)
        
        if next_url and next_url != initial_url:
            self.logger.info(f"AI decided to navigate to: {next_url}")
            # Check if we need to navigate further
            new_page_content = self._get_page_content(next_url)
            if new_page_content:
                self.logger.info("Got content from new page, checking if we need to navigate further...")
                final_url = self._ai_evaluate_and_navigate(next_url, new_page_content)
                if final_url:
                    self.logger.info(f"Final navigation destination: {final_url}")
                    return final_url
            return next_url
        else:
            self.logger.info("AI decided to stay on the original page - skipping re-render")
        
        return initial_url
    
    def _ai_evaluate_and_navigate(self, current_url: str, page_content: str) -> Optional[str]:
        """Evaluate if current page has good internship listings or navigate further."""
        return self._ai_navigate(current_url, page_content)
    
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
        
        self.logger.info(f"Content cleaned (new size: {len(visible_text):,} chars, reduction: {((len(page_content) - len(visible_text)) / len(page_content) * 100):.1f}%)")
        
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
        """AI navigation method to analyze page and decide whether to stay or navigate."""
        content_data = self._extract_clean_content_and_links(page_content, current_url)
        visible_text = content_data['visible_text']
        links = content_data['links']
        
        if not links:
            self.logger.info("No links found for navigation")
            return current_url
        
        # Filter links containing job-related keywords first
        job_keywords = ['jobs', 'intern', 'oppor', 'careers']  # oppor catches opportunity/opportunities
        filtered_links = [link for link in links 
                         if any(keyword in link['text'].lower() or keyword in link['url'].lower() 
                               for keyword in job_keywords)]
        
        # Use filtered links if found, otherwise use all links
        relevant_links = filtered_links if filtered_links else links
        self.logger.info(f"Using {'filtered' if filtered_links else 'all'} links: {len(relevant_links)}/{len(links)}")
        
        links_text = "\n".join(f"{i}. \"{link['text']}\" -> {link['url']}" 
                              for i, link in enumerate(relevant_links, 1))
        
        prompt = f"""You are analyzing a careers website to find internship job listings.

If you see actual job postings with titles and apply buttons/links, return "STAY".
If only general information, look for: "View all internships", "Search internship opportunities", "Apply for internships", "Browse positions", "Job search", "Opportunities"

Return: "STAY", number (1-N) for link to click, or "0" if no relevant links

Analyze this careers page: {current_url}

PAGE CONTENT:
{visible_text[:5000]}

AVAILABLE LINKS TO CLICK:
{links_text}

Does this page show specific internship job listings, or do I need to click a link to find them?

Response (ONLY return 'STAY', a number 1-N, or '0'):"""
        
        response_text = self._llm_query(prompt).upper()
        self.logger.info(f"AI navigation decision: {response_text}")
        
        if response_text == "STAY":
            return current_url
        
        try:
            selection = int(response_text)
            if 1 <= selection <= len(relevant_links):
                selected_link = relevant_links[selection - 1]
                selected_url = selected_link['url']
                self.logger.info(f"AI selected link {selection}: '{selected_link['text']}' -> {selected_url}")
                return selected_url
            elif selection == 0:
                return current_url
        except ValueError:
            pass
        
        return current_url
    
    def _handle_search_bar_interaction(self, url: str, page_content: str) -> Optional[Dict]:
        """Handle search bar detection and interaction if needed."""
        search_analysis = self._llm_analyze_search_need(url, page_content)
        if not search_analysis or not search_analysis.get('needs_search'):
            return None
        return self._perform_search(url, search_analysis)
    
    def _llm_analyze_search_need(self, url: str, page_content: str) -> Optional[Dict]:
        """Use LLM to analyze if we need to search and identify search elements."""
        content_data = self._extract_clean_content_and_links(page_content, url)
        visible_text = content_data['visible_text'][:8000]
        html_structure = content_data['cleaned_html'][:100000]  # Limit HTML for analysis
        
        prompt = f"""Analyze this job board page to determine if search interaction is needed.

URL: {url}

PAGE CONTENT:
{visible_text}

HTML STRUCTURE:
{html_structure}

TASK: Determine if this page shows actual job listings OR needs search interaction.

Return needs_search: FALSE if you see actual job postings with titles and apply buttons.
Return needs_search: TRUE if you only see search forms, filters, or program descriptions.

If needs_search is TRUE, identify the search elements by examining the HTML:

Return ONLY a valid JSON object:
{{
  "needs_search": true/false,
  "search_query": "internship" (or relevant term),
  "search_input_selector": "exact CSS selector for the search input field",
  "search_submit_selector": "exact CSS selector for the submit button/link",
  "reasoning": "brief explanation"
}}

Guidelines:
- Analyze the actual HTML structure to find the real selectors
- search_input_selector: look for input fields with type="text", type="search", or search-related names/ids
- search_submit_selector: look for buttons, links, or elements that trigger search (could be button, a tag, etc.)
- Return the EXACT selectors from the HTML, not generic examples"""

        try:
            result = json.loads(self._llm_query(prompt, json_response=True))
            self.logger.info(f"LLM search analysis: {result.get('reasoning', 'No reasoning provided')}")
            return result
        except Exception as e:
            self.logger.warning(f"LLM search analysis failed: {str(e)}")
            return None
    
    def _perform_search(self, url: str, search_analysis: Dict) -> Optional[Dict]:
        """Perform search interaction using LLM-identified selectors."""
        import time
        try:
            page = self._new_page()
            try:
                page.goto(url, wait_until='networkidle')
                
                search_query = search_analysis.get('search_query', 'intern')
                input_selector = search_analysis.get('search_input_selector', '')
                submit_selector = search_analysis.get('search_submit_selector', '')
                
                self.logger.info(f"Search query: '{search_query}'")
                self.logger.info(f"Input selector: {input_selector}")
                self.logger.info(f"Submit selector: {submit_selector}")
                
                # Fill search field
                if not input_selector or not page.query_selector(input_selector):
                    self.logger.warning("Search input selector not found")
                    return None
                
                page.fill(input_selector, search_query)
                self.logger.info("Filled search field")
                
                # Submit search
                original_url = page.url
                
                if submit_selector and page.query_selector(submit_selector):
                    # Try JavaScript click to bypass overlays
                    try:
                        page.evaluate(f"document.querySelector('{submit_selector}').click()")
                        self.logger.info("Clicked submit element with JavaScript")
                    except Exception:
                        # Fallback to regular click
                        page.click(submit_selector)
                        self.logger.info("Clicked submit element normally")
                else:
                    # Fallback: Try Enter key
                    page.press(input_selector, 'Enter')
                    self.logger.info("Used Enter key fallback")
                
                # Wait for JavaScript/SPA to execute
                time.sleep(10)
                
                # Ask LLM if we successfully reached job listings
                rendered_content = page.evaluate("document.documentElement.outerHTML")
                if self._llm_verify_search_success(rendered_content, page.url):
                    self.logger.info(f"Search successful: {original_url} -> {page.url}")
                    return {'search_performed': True, 'new_url': page.url}
                else:
                    self.logger.warning("Search did not produce job listings")
                    return None
                        
            finally:
                page.close()
        except Exception as e:
            self.logger.error(f"Failed to perform search: {str(e)}")
            return None
    
    def _llm_verify_search_success(self, page_content: str, current_url: str) -> bool:
        """Ask LLM if we successfully reached job listings after search."""
        try:
            # Clean and limit content for LLMcl
            content_data = self._extract_clean_content_and_links(page_content, current_url)
            visible_text = content_data['visible_text'][:5000]  # Smaller limit for quick check
            
            prompt = f"""Did this search successfully load job listings?

URL: {current_url}

PAGE CONTENT:
{visible_text}

Return ONLY "YES" if you see actual job listings with titles, locations, or apply buttons.
Return ONLY "NO" if you see search forms, filters, or general program descriptions without specific job postings."""

            response = self._llm_query(prompt).upper().strip()
            success = response == "YES"
            self.logger.info(f"LLM search verification: {response} -> {success}")
            return success
            
        except Exception as e:
            self.logger.warning(f"LLM search verification failed: {str(e)}")
            return False
    
    def _get_page_content(self, url: str) -> Optional[str]:
        """Get page content using Playwright with Firefox and anti-detection."""
        if url in self._content_cache:
            return self._content_cache[url]
        
        import time
        try:
            page = self._new_page()
            try:
                time.sleep(3)
                page.goto(url, wait_until='networkidle', timeout=60000)
                page.wait_for_load_state("networkidle")
                time.sleep(5)
                
                # Get rendered DOM instead of raw HTML source
                content = page.evaluate("document.documentElement.outerHTML")
                self._content_cache[url] = content
                return content
            finally:
                page.close()
                
        except Exception as e:
            raise Exception(f"Failed to get page content for {url}: {str(e)}")
    
    def _analyze_with_ai(self, url: str, page_content: str) -> Dict:
        """Use AI to analyze the job board structure."""
        # Use the already cleaned HTML from _extract_clean_content_and_links
        content_data = self._extract_clean_content_and_links(page_content, url)
        html_structure = content_data['cleaned_html']
        
        # Limit HTML to first 500,000 characters to avoid token limits
        if len(html_structure) > 500000:
            html_structure = html_structure[:500000]
            self.logger.info(f"HTML truncated to 500,000 characters for LLM analysis")

        system_prompt = """You are an expert web scraper analyzer. Analyze internship job board pages and identify the best way to scrape job listings.

Use the HTML structure to identify specific CSS selectors for job listings.

You MUST return ONLY a valid JSON object with these exact keys:
{
  "job_container_selector": "CSS selector for individual job listings (e.g., \".cmp-jobcard\")",
  "title_selector": "CSS selector for job titles relative to container (e.g., \".cmp-jobcard__title\")",
    "url_selector": "CSS selector for job links relative to container (e.g., \"a\") OR empty string \"\" if container itself has href",
  "description_selector": "CSS selector for descriptions if available (e.g., \".description_text\")",
  "location_selector": "CSS selector for locations if available (e.g., \".cmp-jobcard__location\")",
  "pagination_selector": "CSS selector for pagination/next page (e.g., \".next\")",
  "has_dynamic_loading": true/false (true if the page has dynamic loading, false if it does not)
}

CRITICAL: 
- Return ONLY the JSON object, no other text
- Use actual CSS selectors from the HTML structure
- Do NOT use placeholder names like "job_container_selector" as values"""

        user_prompt = f"""Analyze this internship job board page:

URL: {url}

HTML STRUCTURE:
{html_structure}

Identify specific CSS selectors for scraping internship job listings. Look for repeating HTML patterns that contain job titles, locations, and apply links."""

        combined_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        response = self.client.models.generate_content(
            model=gemini_model,
            contents=combined_prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": JobBoardAnalysis,
            }
        )
        
        self.logger.info(f"LLM Raw Response: {response.text}")
        
        # Use the parsed response directly
        analysis_obj: JobBoardAnalysis = response.parsed
        self.logger.info(f"Successfully parsed structured response: {analysis_obj}")
        
        # Convert to dict for compatibility with existing code
        analysis = {
            "job_container_selector": analysis_obj.job_container_selector,
            "title_selector": analysis_obj.title_selector,
            "url_selector": analysis_obj.url_selector,
            "description_selector": analysis_obj.description_selector,
            "location_selector": analysis_obj.location_selector,
            "pagination_selector": analysis_obj.pagination_selector,
            "has_dynamic_loading": analysis_obj.has_dynamic_loading
        }
        
        return analysis
    
    def _analyze_with_ai_and_feedback(self, url: str, html_structure: str, previous_feedback: Dict) -> Dict:
        """AI analysis with feedback from previous failed attempts."""
        self.logger.info(f"Re-analyzing with feedback from attempt {previous_feedback['attempt']}")
        
        # Limit HTML to avoid token limits
        if len(html_structure) > 500000:
            html_structure = html_structure[:500000]
            self.logger.info("HTML truncated to 500,000 characters for LLM analysis")

        system_prompt = """You are an expert web scraper analyzer. You previously analyzed this page but the selectors didn't work well. 

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

CRITICAL: 
- Return ONLY the JSON object, no other text
- Use actual CSS selectors from the HTML structure
- Learn from the previous attempt's issues
- Be more specific/different than the previous selectors that failed"""

        user_prompt = f"""RETRY ANALYSIS - Previous attempt failed.

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

        combined_prompt = f"{system_prompt}\n\n{user_prompt}"

        response = self.client.models.generate_content(
            model=gemini_model,
            contents=combined_prompt,
            config={
                "response_mime_type": "application/json",
                "response_schema": JobBoardAnalysis,
            }
        )
        
        self.logger.info(f"LLM Raw Response: {response.text}")
        
        # Use the parsed response directly
        analysis_obj: JobBoardAnalysis = response.parsed
        self.logger.info(f"Successfully parsed structured response: {analysis_obj}")
        
        # Convert to dict for compatibility with existing code
        analysis = {
            "job_container_selector": analysis_obj.job_container_selector,
            "title_selector": analysis_obj.title_selector,
            "url_selector": analysis_obj.url_selector,
            "description_selector": analysis_obj.description_selector,
            "location_selector": analysis_obj.location_selector,
            "pagination_selector": analysis_obj.pagination_selector,
            "has_dynamic_loading": analysis_obj.has_dynamic_loading
        }
        
        return analysis
    
    def _wait_before_retry(self, attempt: int):
        """Wait with exponential backoff before retry."""
        wait_time = min(2 ** attempt, 30)  # Cap at 30 seconds
        self.logger.info(f"Waiting {wait_time} seconds before retry...")
        time.sleep(wait_time)
    
    def _analyze_with_ai_with_feedback(self, url: str, html_structure: str, previous_feedback: Optional[Dict]) -> Dict:
        """AI analysis with feedback from previous attempts."""
        try:
            if previous_feedback:
                # Include feedback from previous attempt
                return self._analyze_with_ai_and_feedback(url, html_structure, previous_feedback)
            else:
                # First attempt, use original method
                return self._analyze_with_ai(url, html_structure)
        except Exception as e:
            self.logger.error(f"AI analysis failed: {str(e)}")
            return {"error": f"AI analysis failed: {str(e)}"}
    
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
            import threading
            
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
                test_config = {
                    'company_name': analysis.get('company_name', 'Test Company'),
                    'job_container_selector': analysis.get('job_container_selector', ''),
                    'title_selector': analysis.get('title_selector', ''),
                    'url_selector': analysis.get('url_selector', ''),
                    'description_selector': analysis.get('description_selector', ''),
                    'location_selector': analysis.get('location_selector', ''),
                    'pagination_selector': analysis.get('pagination_selector', ''),
                    'max_pages': 1  # Only test first page for validation
                }
                
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
        if len(html_structure) > 200000:
            html_structure = html_structure[:200000]
        
        # Prepare job sample
        job_sample = jobs[:3] if jobs else []
        
        system_prompt = """You are evaluating a job scraper configuration. Analyze the test results and determine if the config is good or needs improvement. You have been fed the first 3 jobs extracted as a sample.

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
  * At least some jobs were extracted with titles and URLs

- OPTIONAL ELEMENTS (empty/missing is acceptable):
  * Description selector - job pages may not have descriptions on listing pages
  * Location selector - some sites don't show location in listings
  * Requirements selector - often not available on listing pages
  * Pagination selector - only needed if site has multiple pages

- EVALUATION FOCUS:
  * Only flag issues with selectors that are failing to work when they should
  * Don't penalize empty optional selectors - they may be intentionally empty
  * Focus on whether the scraper successfully extracts the core job data (title, URL)
  * Consider the context: listing pages vs detail pages have different available data

Only recommend retry if CRITICAL selectors are broken or no jobs are being extracted."""

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

        try:
            print(json.dumps(job_sample, indent=2))
            evaluation = json.loads(self._llm_query(f"{system_prompt}\n\n{user_prompt}", json_response=True))
            self.logger.info(f"LLM evaluation: {evaluation.get('success')}")
            return evaluation
            
        except Exception as e:
            self.logger.error(f"LLM evaluation failed: {str(e)}")
            # If LLM fails, we must retry - no fallback logic
            return {
                "success": False,
                "issues": ["LLM evaluation failed"],
                "suggestions": ["Retry analysis"],
                "retry_recommended": True
            }
    
    def generate_scraper_config(self, company_name: str, url: str, analysis: Dict) -> Dict:
        """Generate Playwright scraper configuration."""
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
            'max_pages': 999,  # Unlimited - will stop automatically based on end conditions
            'created_at': datetime.now().isoformat()
        }
    
    def generate_scraper_script(self, company_name: str, url: str, analysis: Dict) -> str:
        """Generate a standalone Python script that uses PlaywrightScraper."""
        scrape_url = analysis.get("final_url", url)
        
        # Read the template file
        template_path = os.path.join(os.path.dirname(__file__), 'scraper_template.py')
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()
        except FileNotFoundError:
            self.logger.error(f"Template file not found: {template_path}")
            raise FileNotFoundError(f"Scraper template file not found at {template_path}")
        
        # Prepare template variables
        template_vars = {
            'company_name': company_name,
            'scrape_url': scrape_url,
            'generated_at': datetime.now().isoformat(),
            'log_filename': f"{company_name.lower().replace(' ', '_')}_scraper.log",
            'job_container_selector': analysis.get('job_container_selector', ''),
            'title_selector': analysis.get('title_selector', ''),
            'url_selector': analysis.get('url_selector', ''),
            'description_selector': analysis.get('description_selector', ''),
            'location_selector': analysis.get('location_selector', ''),
            'requirements_selector': analysis.get('requirements_selector', ''),
            'pagination_selector': analysis.get('pagination_selector', ''),
            'has_dynamic_loading': str(analysis.get('has_dynamic_loading', False)),
            'backup_filename': f"{company_name.lower().replace(' ', '_')}_jobs_{int(datetime.now().timestamp())}.json"
        }
        
        # Fill in the template
        try:
            generated_script = template_content.format(**template_vars)
            return generated_script
        except KeyError as e:
            self.logger.error(f"Missing template variable: {e}")
            raise ValueError(f"Template variable missing: {e}")
        except Exception as e:
            self.logger.error(f"Error generating script from template: {e}")
            raise RuntimeError(f"Script generation failed: {e}")
