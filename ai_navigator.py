import json
import logging
import time
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from google import genai
import os
from datetime import datetime
from dotenv import load_dotenv
from pydantic import BaseModel
from config import Config

load_dotenv()

class JobBoardAnalysis(BaseModel):
    job_container_selector: str
    title_selector: str
    url_selector: str
    description_selector: str
    location_selector: str
    pagination_selector: str
    has_dynamic_loading: bool

class AINavigator:
    """AI-powered website navigation and scraper generation using Gemini."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
        self._page_cache = {}  # Cache for cleaned page content
        self._content_cache = {}  # Cache for raw page content
    
    def analyze_job_board(self, url: str) -> Dict:
        """Analyze a job board website and identify scraping targets with retry mechanism."""
        self.logger.info(f"Analyzing job board: {url}")
        
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
    
    def _find_internship_page(self, initial_url: str) -> Optional[str]:
        """Navigate from a general careers page to the specific internship page."""
        self.logger.info(f"Starting navigation from: {initial_url}")
        
        page_content = self._get_page_content(initial_url)
        if not page_content:
            self.logger.warning("Could not get page content")
            return initial_url
        
        self.logger.info("Got page content, analyzing with AI for navigation...")
        
        # Have AI decide what to click
        next_url = self._ai_click_navigation(initial_url, page_content)
        
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
        
        soup = BeautifulSoup(page_content, 'html.parser')
        
        # Remove all HTML comments (notes)
        from bs4 import Comment
        comments = soup.find_all(string=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment.extract()
        
        # Remove irrelevant sections by tag
        irrelevant_tags = [
            # Original list
            'script', 'style', 'meta', 'link', 'noscript',
            'header', 'footer', 'nav', 'aside',
            
            # Newly added tags
            'svg', 'dialog', 'template',
            'canvas', 'audio', 'video'
        ]
        
        for tag_name in irrelevant_tags:
            for element in soup.find_all(tag_name):
                element.decompose()
        
        # Remove elements by common class/id patterns
        irrelevant_selectors = [
            # Navigation and headers
            '.header', '.footer', '.nav', '.navigation', '.navbar', '.menu',
            '.breadcrumb', '.breadcrumbs', '.sidebar', '.aside',
            '#header', '#footer', '#nav', '#navigation', '#navbar', '#menu',
            
            # Cookie/privacy/legal
            '.cookie-banner', '.cookie-notice', '.privacy-notice', '.legal-notice',
            '.disclaimer', '.gdpr', '.consent',
            
            # Social media and sharing
            '.social-media', '.social-links', '.social-share', '.share-buttons',
            '.follow-us', '.social-icons', '.share', '.sharing',
            
            # Advertisements
            '.advertisement', '.ads', '.ad-banner', '.sponsored', '.promo',
            '.banner', '.popup', '.modal',
            
            # Comments and user content
            '.comments', '.comment-section', '.reviews', '.testimonials',
            '.user-comments', '.feedback',
            
            # Newsletter and forms (non-job related)
            '.newsletter-signup', '.subscribe-form', '.signup-form',
            
            # Utility elements
            '.back-to-top', '.scroll-to-top', '.skip-link'
        ]
        
        for selector in irrelevant_selectors:
            for element in soup.select(selector):
                element.decompose()
        
        # Keyword-based filtering removed to preserve pagination elements
        
        # Only truncate raw text nodes in divs, preserve links and structure
        for div in soup.find_all('div'):
            # Only process divs that have direct text content (not just nested elements)
            if div.string and len(div.string.strip()) > 100:
                # Only truncate if this div contains just text, no nested elements like links
                div.string.replace_with(div.string[:100] + "... [TRUNCATED]")
        
        # Apply whitespace stripping and empty line removal to HTML
        cleaned_html_str = self._strip_whitespace_and_empty_lines(str(soup))
        
        # Extract visible text from cleaned content
        visible_text = soup.get_text(separator=' ', strip=True)
        visible_text = ' '.join(visible_text.split())  # Clean whitespace
        
        self.logger.info(f"Content cleaned (new size: {len(visible_text):,} chars, reduction: {((len(page_content) - len(visible_text)) / len(page_content) * 100):.1f}%)")
        
        # Extract links from cleaned content
        links = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '').strip()
            if href and not href.startswith(('javascript:', 'mailto:', 'tel:', '#')):
                absolute_url = urljoin(base_url, href)
                link_text = link.get_text(strip=True)
                if link_text:  # Only include links with text
                    links.append({
                        'text': link_text,
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
    
    def _strip_whitespace_and_empty_lines(self, html_content: str) -> str:
        """Strip all whitespace and remove empty lines from HTML content."""
        try:
            # Split content into lines
            lines = html_content.split('\n')
            
            # Process each line: strip whitespace and filter out empty lines
            cleaned_lines = []
            for line in lines:
                stripped_line = line.strip()
                if stripped_line:  # Only keep non-empty lines
                    cleaned_lines.append(stripped_line)
            
            # Join lines back together
            return '\n'.join(cleaned_lines)
        except Exception as e:
            self.logger.warning(f"Error stripping whitespace: {str(e)}")
            return html_content
    
    def _ai_click_navigation(self, current_url: str, page_content: str) -> Optional[str]:
        """Have AI analyze the page content and decide which link to click."""
        return self._ai_navigate(current_url, page_content)
    
    def _ai_navigate(self, current_url: str, page_content: str) -> Optional[str]:
        """AI navigation method to analyze page and decide whether to stay or navigate."""
        content_data = self._extract_clean_content_and_links(page_content, current_url)
        visible_text = content_data['visible_text']
        links = content_data['links']
        
        if not links:
            self.logger.info("No links found for navigation")
            return current_url
        
        # Filter links containing job-related keywords first
        job_keywords = ['jobs', 'intern', 'oppor']  # oppor catches opportunity/opportunities
        filtered_links = [link for link in links 
                         if any(keyword in link['text'].lower() for keyword in job_keywords)]
        
        # Use filtered links if found, otherwise use all links
        relevant_links = filtered_links if filtered_links else links
        self.logger.info(f"Using {'filtered' if filtered_links else 'all'} links: {len(relevant_links)}/{len(links)}")
        
        links_text = "\n".join(f"{i}. \"{link['text']}\" -> {link['url']}" 
                              for i, link in enumerate(relevant_links, 1))
        
        system_prompt = """You are analyzing a careers website to find internship job listings.

If you see actual job postings with titles and apply buttons/links, return "STAY".
If only general information, look for: "View all internships", "Search internship opportunities", "Apply for internships", "Browse positions", "Job search", "Opportunities"

Return: "STAY", number (1-N) for link to click, or "0" if no relevant links"""
        
        user_prompt = f"""Analyze this careers page: {current_url}

PAGE CONTENT:
{visible_text[:5000]}

AVAILABLE LINKS TO CLICK:
{links_text}

Does this page show specific internship job listings, or do I need to click a link to find them?"""
        
        combined_prompt = f"{system_prompt}\n\n{user_prompt}\n\nResponse (ONLY return 'STAY', a number 1-N, or '0'):"
        
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=combined_prompt
        )
        
        response_text = response.text.strip().upper()
        self.logger.info(f"AI navigation decision: {response_text}")
        
        if response_text == "STAY":
            return current_url
        
        try:
            selection = int(response_text)
            if 1 <= selection <= len(relevant_links):
                selected_link = relevant_links[selection - 1]
                self.logger.info(f"AI selected link {selection}: '{selected_link['text']}' -> {selected_link['url']}")
                return selected_link['url']
            elif selection == 0:
                return current_url
        except ValueError:
            pass
        
        return current_url
    
    def _get_page_content(self, url: str) -> Optional[str]:
        """Get page content using Playwright with Firefox and anti-detection."""
        # Check cache first
        if url in self._content_cache:
            self.logger.info(f"Using cached page content for {url}")
            return self._content_cache[url]
        
        from playwright.sync_api import sync_playwright
        import time
        import random
        
        try:
            with sync_playwright() as p:
                browser = p.firefox.launch(
                    headless=True,
                    firefox_user_prefs={
                        "javascript.enabled": True,
                        "dom.webdriver.enabled": False,
                        "useAutomationExtension": False,
                        "general.useragent.override": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
                    }
                )
                
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
                )
                
                page = context.new_page()
                
                page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
                """)
                
                time.sleep(3)
                page.goto(url, wait_until='networkidle', timeout=60000)
                page.wait_for_load_state("networkidle")
                time.sleep(5)  # Wait 5 seconds for all dynamic content to load
                
                content = page.content()
                browser.close()
                
                # Cache the content
                self._content_cache[url] = content
                
                return content
                
        except Exception:
            # Simple requests fallback
            try:
                session = requests.Session()
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0'
                })
                
                response = session.get(url, timeout=30)
                if response.status_code == 200:
                    # Cache the fallback content too
                    self._content_cache[url] = response.text
                    return response.text
            except Exception:
                pass
                
        return None
    
    def _analyze_with_ai(self, url: str, page_content: str) -> Dict:
        """Use AI to analyze the job board structure."""
        # Use the already cleaned HTML from _extract_clean_content_and_links
        content_data = self._extract_clean_content_and_links(page_content, url)
        html_structure = content_data['cleaned_html']
        
        # Limit HTML to first 500,000 characters to avoid token limits
        if len(html_structure) > 500000:
            html_structure = html_structure[:500000]
            self.logger.info(f"HTML truncated to 300,000 characters for LLM analysis")

        system_prompt = """You are an expert web scraper analyzer. Analyze internship job board pages and identify the best way to scrape job listings.

Use the HTML structure to identify specific CSS selectors for job listings.

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
- Do NOT use placeholder names like "job_container_selector" as values"""

        user_prompt = f"""Analyze this internship job board page:

URL: {url}

HTML STRUCTURE:
{html_structure}

Identify specific CSS selectors for scraping internship job listings. Look for repeating HTML patterns that contain job titles, locations, and apply links."""

        combined_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
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
            model="gemini-2.5-flash",
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
        """LLM-focused validation: gather all test results and let LLM evaluate."""
        self.logger.info("Starting LLM-focused config validation...")
        
        try:
            # Import here to avoid circular imports
            from playwright_scraper import PlaywrightScraperSync
            scraper = PlaywrightScraperSync()
            
            # Test all selectors
            selectors_to_test = {
                'job_container_selector': analysis.get('job_container_selector', ''),
                'title_selector': analysis.get('title_selector', ''),
                'url_selector': analysis.get('url_selector', ''),
                'description_selector': analysis.get('description_selector', ''),
                'location_selector': analysis.get('location_selector', ''),
                'pagination_selector': analysis.get('pagination_selector', '')
            }
            
            # Filter out empty selectors
            non_empty_selectors = {k: v for k, v in selectors_to_test.items() if v.strip()}
            
            # Test job extraction (this also tests selectors)
            test_config = {
                'company_name': 'TestCompany',
                'scrape_url': url,
                'job_container_selector': analysis.get('job_container_selector', ''),
                'title_selector': analysis.get('title_selector', ''),
                'url_selector': analysis.get('url_selector', ''),
                'description_selector': analysis.get('description_selector', ''),
                'location_selector': analysis.get('location_selector', ''),
                'pagination_selector': analysis.get('pagination_selector', ''),
                'has_dynamic_loading': analysis.get('has_dynamic_loading', False),
                'max_pages': 1
            }
            
            jobs, _ = scraper.scrape_jobs(url, test_config)
            
            # Create mock selector results based on job extraction success
            selector_results = {
                'url': url,
                'test_time': datetime.now().isoformat(),
                'results': {
                    'job_container_selector': {
                        'selector': analysis.get('job_container_selector', ''),
                        'elements_found': len(jobs),
                        'success': len(jobs) > 0
                    },
                    'title_selector': {
                        'selector': analysis.get('title_selector', ''),
                        'success': any(job.get('title', '').strip() for job in jobs)
                    },
                    'url_selector': {
                        'selector': analysis.get('url_selector', ''),
                        'success': any(job.get('url', '').strip() for job in jobs)
                    }
                }
            }
            
            # Simple pagination test - just check if selector exists and jobs were found
            pagination_test = {}
            if analysis.get('pagination_selector'):
                pagination_test = {
                    "pagination_selector": analysis.get('pagination_selector', ''),
                    "jobs_found": len(jobs),
                    "test_attempted": True,
                    "success": len(jobs) > 0
                }
            
            # Let LLM evaluate all results
            return self._llm_evaluate_config(analysis, selector_results, jobs, pagination_test, html_structure, url)
            
        except Exception as e:
            return {"success": False, "error": f"Validation failed: {str(e)}"}
    
    
    def _llm_evaluate_config(self, analysis: Dict, selector_results: Dict, jobs: List[Dict], pagination_test: Dict, html_structure: str, url: str) -> Dict:
        """Let LLM evaluate the config based on all test results."""
        self.logger.info("LLM evaluating config results...")
        
        # Limit HTML to avoid token limits
        if len(html_structure) > 200000:
            html_structure = html_structure[:200000]
        
        # Prepare job sample
        job_sample = jobs[:5] if jobs else []
        
        system_prompt = """You are evaluating a job scraper configuration. Analyze the test results and determine if the config is good or needs improvement.

Return ONLY a valid JSON object with these exact keys:
{
  "success": true/false,
  "issues": ["list of specific issues found"],
  "suggestions": ["list of specific improvements"],
  "retry_recommended": true/false
}

Criteria for success:
- Job container selector finds elements
- Title selector extracts job titles successfully  
- URL selector extracts valid job links
- At least some jobs were extracted
- If pagination selector provided, it should work

If critical selectors fail or no jobs found, recommend retry."""

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
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"{system_prompt}\n\n{user_prompt}",
                config={
                    "response_mime_type": "application/json"
                }
            )
            
            evaluation = json.loads(response.text)
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
        
        script_template = f'''#!/usr/bin/env python3
"""
Playwright-based job scraper for {company_name}
Generated automatically by AI Navigator
URL: {scrape_url}
Generated at: {datetime.now().isoformat()}
"""

import json
import logging
import sys
import os
from datetime import datetime

# Add the parent directory to the path to import our modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright_scraper import PlaywrightScraperSync
from database import DatabaseManager


def setup_logging():
    """Setup logging for the scraper."""
    import os
    os.makedirs('logs', exist_ok=True)
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f'logs/{company_name.lower().replace(" ", "_")}_scraper.log'),
            logging.StreamHandler()
        ]
    )


def get_scraper_config():
    """Get the scraper configuration for {company_name}."""
    return {{
        'company_name': '{company_name}',
        'scrape_url': '{scrape_url}',
        'job_container_selector': '{analysis.get("job_container_selector", "")}',
        'title_selector': '{analysis.get("title_selector", "")}',
        'url_selector': '{analysis.get("url_selector", "")}',
        'description_selector': '{analysis.get("description_selector", "")}',
        'location_selector': '{analysis.get("location_selector", "")}',
        'requirements_selector': '{analysis.get("requirements_selector", "")}',
        'pagination_selector': '{analysis.get("pagination_selector", "")}',
        'has_dynamic_loading': {str(analysis.get("has_dynamic_loading", False))},
        'max_pages': 999  # Unlimited - will stop automatically based on end conditions
    }}


def main():
    """Main scraper function."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    logger.info("Starting {company_name} job scraper...")
    
    config = get_scraper_config()
    
    # Initialize database-enabled scraper
    scraper = PlaywrightScraperSync(use_database=True)
    db_manager = DatabaseManager()
    
    # Get company info from database
    company = db_manager.get_company_by_name('{company_name}')
    if not company:
        logger.error("Company '{company_name}' not found in database")
        print("Error: Company not found in database. Please add the company first.")
        return
    
    # Update last scraped timestamp
    db_manager.update_company_scraper(company['id'], "")
    
    # Scrape jobs and get filtered HTML
    jobs, filtered_html = scraper.scrape_jobs(config['scrape_url'], config)
    
    if jobs:
        logger.info(f"Successfully scraped {{len(jobs)}} jobs from {company_name}")
        
        # Print summary
        print(f"\\n=== SCRAPING RESULTS ===")
        print(f"Company: {company_name}")
        print(f"URL: {scrape_url}")
        print(f"Jobs found: {{len(jobs)}}")
        print(f"Jobs saved to database: jobs.db")
        
        # Show sample jobs
        print(f"\\n=== SAMPLE JOBS ===")
        for i, job in enumerate(jobs[:3], 1):
            print(f"{{i}}. {{job.get('title', 'No title')}}")
            print(f"   Location: {{job.get('location', 'Not specified')}}")
            print(f"   URL: {{job.get('url', 'No URL')}}")
            print()
            
        # Optional: Also save as JSON backup if needed
        # output_file = f'{company_name.lower().replace(" ", "_")}_jobs_{{int(datetime.now().timestamp())}}.json'
        # with open(output_file, 'w', encoding='utf-8') as f:
        #     json.dump(jobs, f, indent=2, ensure_ascii=False)
        # print(f"Backup JSON saved to: {{output_file}}")
        
    else:
        logger.warning("No jobs found - scraper may need adjustment")
        print("No jobs found. The scraper configuration may need to be adjusted.")
        
        # Log failed scraper execution
        db_manager.log_scraper_execution(
            company['id'], 
            0, 
            success=False,
            error_message="No jobs found"
        )


if __name__ == "__main__":
    main()
'''
        
        return script_template
    
    def evaluate_scraper_performance(self, scraped_data: List[Dict]) -> Dict:
        """Simple scraper performance evaluation."""
        total_jobs = len(scraped_data)
        jobs_with_titles = sum(1 for job in scraped_data if job.get('title', '').strip())
        jobs_with_urls = sum(1 for job in scraped_data if job.get('url', '').strip())
        
        success = jobs_with_titles > 0 and jobs_with_urls > 0 and total_jobs >= 1
        
        return {
            "success": success,
            "total_jobs": total_jobs,
            "jobs_with_titles": jobs_with_titles,
            "jobs_with_urls": jobs_with_urls
        }