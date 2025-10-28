import asyncio
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from html_cleaning_utils import clean_html_content_comprehensive

def clean_extracted_text(text: str) -> str:
    """Clean extracted text by removing extra whitespace and newlines."""
    if not text:
        return ""
    # Strip whitespace and collapse multiple whitespace/newlines into single spaces
    return ' '.join(text.strip().split())

class PlaywrightScraper:
    """
    Playwright-based job scraper that can execute dynamically generated scraper scripts.
    """
    
    def __init__(self, db_manager=None):
        self.logger = logging.getLogger(__name__)
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.db_manager = db_manager
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.start_browser()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close_browser()
    
    async def start_browser(self):
        """Initialize browser with anti-detection settings."""
        self.logger.info("Starting Playwright browser...")
        
        self.playwright = await async_playwright().start()
        
        self.browser = await self.playwright.firefox.launch(
            headless=True,
            firefox_user_prefs={
                "javascript.enabled": True,
                "dom.webdriver.enabled": False,
                "useAutomationExtension": False,
            }
        )
        
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
            }
        )
        
        self.logger.info("Browser started successfully")
    
    async def close_browser(self):
        """Close browser and cleanup."""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()
        
        self.logger.info("Browser closed")
    
    async def scrape_jobs(self, url: str, scraper_config: Dict) -> Tuple[List[Dict], str]:
        """
        Scrape jobs from a URL using the provided scraper configuration.
        
        Args:
            url: The URL to scrape
            scraper_config: Configuration containing selectors and scraping strategy
            
        Returns:
            Tuple of (List of job dictionaries, filtered HTML content)
        """
        self.logger.info(f"Starting job scraping for: {url}")
        
        if not self.browser:
            await self.start_browser()
        
        page = await self.context.new_page()
        
        try:
            # Add anti-detection script
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined,
                });
            """)
            
            await asyncio.sleep(3)
            
            # Try networkidle first, but if it times out just continue with whatever loaded
            try:
                await page.goto(url, wait_until='networkidle', timeout=30000)
            except Exception as e:
                self.logger.warning(f"Timeout after 30s while loading {url}. Proceeding with available page content.")
            
            # Wait 5 seconds for all dynamic content to load
            self.logger.info("Waiting 5 seconds for all content to load...")
            await asyncio.sleep(5)
            
            # Dismiss any overlays that might interfere with scraping
            await self._dismiss_overlays(page)
            
            # Perform search if required
            if scraper_config.get('search_required', False):
                await self._perform_search_interaction(page, scraper_config)
                
                # Wait for dynamic content to load after interaction
                self.logger.info("Waiting 5 seconds for dynamic content after interaction...")
                await asyncio.sleep(5)
            
            # Clean page HTML to remove irrelevant sections (same as ai_navigator)
            # This ensures selectors work consistently between analysis and production scraping
            self.logger.info("Cleaning page HTML to remove irrelevant sections...")
            raw_html = await page.content()
            cleaned_html = clean_html_content_comprehensive(raw_html, self.logger)
            
            # Inject cleaned HTML back into page so selectors work on cleaned structure
            await page.set_content(cleaned_html, wait_until='domcontentloaded')
            
            # Extract jobs using the configuration
            jobs = await self._extract_jobs_from_page(page, scraper_config, url)
            
            # Handle pagination if configured
            if scraper_config.get('pagination_selector') and scraper_config.get('max_pages', 1) > 1:
                additional_jobs = await self._handle_pagination(page, scraper_config, url, jobs)
                jobs.extend(additional_jobs)
            
            self.logger.info(f"Successfully scraped {len(jobs)} jobs")
            return jobs, cleaned_html
            
        except Exception as e:
            self.logger.error(f"Error scraping jobs from {url}: {str(e)}")
            return [], ""
        finally:
            await page.close()
    
    async def _extract_jobs_from_page(self, page: Page, config: Dict, base_url: str) -> List[Dict]:
        """Extract jobs from the current page using the scraper configuration."""
        jobs = []
        
        # Always use main page - iframe content is already rendered inline by ai_navigator
        target_frame = page
        
        try:
            # Get job containers (dynamic content should already be loaded and HTML cleaned)
            container_selector = config.get('job_container_selector', '')
            if not container_selector:
                self.logger.error("No job container selector provided")
                return []
            
            # Check if text filtering is needed
            text_filter_keywords = config.get('text_filter_keywords', '').strip()
            
            if text_filter_keywords:
                # Use Playwright's filter method with hasText for internship filtering
                keywords = [kw.strip() for kw in text_filter_keywords.split(',') if kw.strip()]
                keyword_pattern = '|'.join(re.escape(keyword) for keyword in keywords)
                
                self.logger.info(f"Applying text filter for keywords: {keywords}")
                
                # Filter job containers by text content using Playwright's filter()
                job_locator = target_frame.locator(container_selector)
                total_containers = await job_locator.count()
                filtered_locator = job_locator.filter(has_text=re.compile(keyword_pattern, re.IGNORECASE))
                job_elements = await filtered_locator.all()
                
                self.logger.info(f"Found {len(job_elements)} job containers matching internship keywords out of {total_containers} total containers")
            else:
                # Use locator().all() to get Locator objects (not ElementHandles)
                job_elements = await target_frame.locator(container_selector).all()
                self.logger.info(f"Found {len(job_elements)} job containers (no text filtering)")
            
            for idx, job_element in enumerate(job_elements):
                try:
                    job_data = await self._extract_job_data(job_element, config, base_url)
                    if job_data and job_data.get('title') and job_data.get('url'):
                        jobs.append(job_data)
                    elif job_data:
                        self.logger.warning(f"Job container {idx+1}/{len(job_elements)} rejected - missing title or URL. Title: '{job_data.get('title', 'EMPTY')}', URL: '{job_data.get('url', 'EMPTY')}'")
                    else:
                        self.logger.warning(f"Job container {idx+1}/{len(job_elements)} rejected - _extract_job_data returned None")
                except Exception as e:
                    self.logger.warning(f"Error extracting job data from container {idx+1}/{len(job_elements)}: {type(e).__name__}: {str(e)}")
                    continue
            
        except Exception as e:
            self.logger.error(f"Error extracting jobs from page: {str(e)}")
        
        return jobs
    
    async def _extract_job_data(self, job_element, config: Dict, base_url: str) -> Optional[Dict]:
        """Extract data from a single job element."""
        job_data = {
            'scraped_at': datetime.now().isoformat(),
            'company': config.get('company_name', ''),
            'title': '',
            'url': '',
            'description': '',
            'location': '',
            'requirements': ''
        }

        try:
            # Define field mappings for dynamic extraction
            field_mappings = {
                'title': 'title_selector',
                'description': 'description_selector',
                'location': 'location_selector',
                'requirements': 'requirements_selector'
            }

            # Extract text-based fields dynamically
            for field_name, selector_key in field_mappings.items():
                selector = config.get(selector_key, '')
                
                if selector:
                    try:
                        element_locator = job_element.locator(selector).first
                        text = await element_locator.text_content(timeout=100) or ''
                        cleaned_text = clean_extracted_text(text)
                        job_data[field_name] = cleaned_text
                        if cleaned_text:
                            self.logger.debug(f"Extracted {field_name}: {cleaned_text[:50]}...")
                        else:
                            self.logger.debug(f"Extracted {field_name} but result was empty after cleaning")
                    except Exception as e:
                        self.logger.warning(f"Failed to extract {field_name} using selector '{selector}': {type(e).__name__}: {str(e)}")
                        pass  # Element not found, skip
                else:
                    if field_name == 'title':
                        self.logger.warning(f"No {selector_key} configured in scraper config!")

            # Handle URL extraction separately (requires href attribute)
            url_selector = config.get('url_selector', '')
            url_extracted = False
            
            # Try container first (common case: container IS the <a> tag)
            try:
                href = await job_element.get_attribute('href', timeout=1000)
                if href:
                    job_data['url'] = urljoin(base_url, href.strip())
                    self.logger.debug(f"Extracted URL from container href: {job_data['url']}")
                    url_extracted = True
            except Exception as e:
                self.logger.debug(f"Container href extraction failed: {type(e).__name__}")
            
            # If container didn't have href, try child element with url_selector
            if not url_extracted and url_selector:
                try:
                    url_locator = job_element.locator(url_selector).first
                    href = await url_locator.get_attribute('href', timeout=1000)
                    if href:
                        job_data['url'] = urljoin(base_url, href.strip())
                        self.logger.debug(f"Extracted URL from selector '{url_selector}': {job_data['url']}")
                        url_extracted = True
                except Exception as e2:
                    self.logger.warning(f"Failed to extract URL using selector '{url_selector}': {type(e2).__name__}: {str(e2)}")
            
            # Warn if no URL was extracted
            if not url_extracted:
                if not url_selector:
                    self.logger.warning(f"No URL extracted - container has no href and no url_selector provided in config")
                else:
                    self.logger.warning(f"No URL extracted - both container href and url_selector '{url_selector}' failed")
            
        except Exception as e:
            self.logger.error(f"Unexpected error extracting job data: {type(e).__name__}: {str(e)}")
            import traceback
            self.logger.debug(traceback.format_exc())
            return None

        # Debug log final extracted data
        if not job_data['title']:
            self.logger.warning(f"Job rejected - no title extracted. URL: {job_data.get('url', 'N/A')}, Config selectors: title_selector='{config.get('title_selector', 'MISSING')}'")
        elif not job_data['url']:
            self.logger.warning(f"Job rejected - no URL extracted. Title: '{job_data['title']}', Config selectors: url_selector='{config.get('url_selector', 'MISSING')}'")
        
        return job_data if (job_data['title'] and job_data['url']) else None
    
    async def _handle_pagination(self, page: Page, config: Dict, base_url: str, initial_jobs: List[Dict] = None) -> List[Dict]:
        """Handle intelligent pagination until end conditions are met."""
        all_jobs = []
        max_pages = config.get('max_pages', 5)  # Default to high number for unlimited pagination
        pagination_selector = config.get('pagination_selector', '')
        
        # Keep track of all scraped URLs to detect duplicates, starting with initial page jobs
        all_scraped_urls = set()
        if initial_jobs:
            all_scraped_urls.update({job.get('url', '') for job in initial_jobs if job.get('url')})
        
        # If database is available, get existing URLs for more comprehensive duplicate detection
        existing_db_urls = set()
        if self.db_manager and config.get('company_name'):
            try:
                company = self.db_manager.get_company_by_name(config.get('company_name'))
                if company:
                    existing_db_urls = self.db_manager.get_existing_job_urls(company['id'])
                    self.logger.info(f"Found {len(existing_db_urls)} existing jobs in database for duplicate checking")
            except Exception as e:
                self.logger.warning(f"Could not load existing job URLs from database: {str(e)}")
        
        # Combine scraped URLs with database URLs for comprehensive duplicate detection
        all_known_urls = all_scraped_urls.union(existing_db_urls)
        
        page_num = 2
        while page_num <= max_pages:
            try:
                self.logger.info(f"Attempting to navigate to page {page_num}")
                
                # Dismiss any overlays that might block pagination
                await self._dismiss_overlays(page)
                
                # Look for next page link
                next_link = await page.query_selector(pagination_selector)
                if not next_link:
                    self.logger.info(f"No next page link found on page {page_num-1} - pagination complete")
                    break
                
                # Check if link is disabled or hidden
                is_disabled = await next_link.get_attribute('disabled')
                is_hidden = await next_link.is_hidden()
                class_attr = await next_link.get_attribute('class') or ''
                
                if is_disabled or is_hidden or 'disabled' in class_attr.lower():
                    self.logger.info(f"Next page link is disabled/hidden on page {page_num-1} - pagination complete")
                    break
                
                # Check if the link is actually clickable
                try:
                    is_clickable = await next_link.is_enabled()
                    if not is_clickable:
                        self.logger.info(f"Next page link is not clickable on page {page_num-1} - pagination complete")
                        break
                except:
                    pass  # Continue if we can't check clickability
                
                # Get current page URL before clicking (for debugging)
                current_url = page.url
                
                # Click next page using JavaScript to bypass overlays
                try:
                    await page.evaluate(f"document.querySelector({repr(pagination_selector)}).click()")
                except Exception as click_error:
                    self.logger.warning(f"Failed to click next page link: {str(click_error)}")
                    break
                
                # Wait for page to load with timeout handling
                try:
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception as e:
                    self.logger.warning(f"Timeout while waiting for page {page_num}. Proceeding with available content.")
                
                await asyncio.sleep(5)
                
                # Check if URL actually changed (some sites don't change URL)
                new_url = page.url
                self.logger.debug(f"URL changed from {current_url} to {new_url}")
                
                # Extract jobs from new page
                page_jobs = await self._extract_jobs_from_page(page, config, base_url)
                
                # Check for end conditions
                if not page_jobs:
                    self.logger.info(f"Page {page_num} has no jobs - stopping pagination")
                    break
                
                # Check for duplicate content against all known jobs (scraped + database)
                current_page_urls = {job.get('url', '') for job in page_jobs if job.get('url')}
                
                # Count duplicates against all known URLs
                duplicate_count = len(current_page_urls.intersection(all_known_urls))
                duplicate_percentage = duplicate_count / len(current_page_urls) if current_page_urls else 0
                
                self.logger.info(f"Page {page_num}: {len(page_jobs)} jobs scraped, {duplicate_count} duplicates ({duplicate_percentage:.1%})")
                
                # Stop if we encounter significant duplicates (>= 50% or all jobs are duplicates)
                if duplicate_count > 0 and (duplicate_percentage >= 0.5 or duplicate_count == len(page_jobs)):
                    self.logger.info(f"Page {page_num}: High duplicate rate ({duplicate_percentage:.1%}) - stopping pagination")
                    break
                
                # Add new (non-duplicate) jobs to results
                new_jobs = [job for job in page_jobs if job.get('url') not in all_known_urls]
                all_jobs.extend(new_jobs)
                
                # Update the sets with newly scraped URLs
                new_urls = {job.get('url', '') for job in new_jobs if job.get('url')}
                all_scraped_urls.update(new_urls)
                all_known_urls.update(new_urls)
                
                self.logger.info(f"Scraped {len(new_jobs)} new jobs from page {page_num} (total new: {len(all_jobs)})")
                
                # If no new jobs were found, stop pagination
                if not new_jobs:
                    self.logger.info(f"Page {page_num}: No new jobs found - stopping pagination")
                    break
                
                page_num += 1
                
                # Add a small delay between pages to be respectful
                await asyncio.sleep(2)
                
            except Exception as e:
                self.logger.error(f"Error handling pagination on page {page_num}: {str(e)}")
                break
        
        self.logger.info(f"Pagination complete. Scraped {len(all_jobs)} additional jobs across {page_num-2} pages")
        return all_jobs
    
    async def _dismiss_overlays(self, page: Page):
        """Remove common overlays that might block interactions."""
        try:
            # Use JavaScript to remove all common overlay patterns at once
            await page.evaluate("""
                // Remove elements that commonly block interactions
                const overlaySelectors = [
                    '[class*="truste"]', '[id*="truste"]',
                    '[class*="cookie"]', '[class*="privacy"]', 
                    '[class*="gdpr"]', '[class*="consent"]',
                    '[style*="z-index: 999"]', '[style*="position: fixed"]'
                ];
                
                overlaySelectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => {
                        if (el.offsetHeight > 0 && el.offsetWidth > 0) {
                            el.remove();
                        }
                    });
                });
            """)
            self.logger.debug("Removed potential overlay elements")
        except Exception as e:
            self.logger.debug(f"Error removing overlays: {str(e)}")
    
    async def _perform_search_interaction(self, page: Page, scraper_config: Dict):
        """Perform search or button interaction when required by the scraper configuration."""
        search_input_selector = scraper_config.get('search_input_selector', '')
        search_submit_selector = scraper_config.get('search_submit_selector', '')
        search_query = scraper_config.get('search_query', '')
        
        # Support two interaction modes:
        # 1. BUTTON MODE: Only submit_selector provided (e.g., "Internships" filter button)
        # 2. SEARCH MODE: input_selector + query provided, with optional submit_selector
        
        is_button_mode = not search_input_selector and not search_query and search_submit_selector
        is_search_mode = search_input_selector and search_query
        
        if not is_button_mode and not is_search_mode:
            self.logger.warning("Search required but insufficient selectors provided (need either button selector OR input selector + query)")
            return
        
        # Always use main page - iframe content is already rendered inline by ai_navigator
        target_frame = page
        
        try:
            if is_button_mode:
                # BUTTON MODE: Click filter/category button directly
                self.logger.info(f"Performing button interaction: clicking '{search_submit_selector}'")
                await page.evaluate(f"document.querySelector({repr(search_submit_selector)}).click()")
                self.logger.info("Clicked filter button successfully")
                
            elif is_search_mode:
                # SEARCH MODE: Fill search input and submit
                self.logger.info(f"Performing search interaction with query: '{search_query}'")
                
                # Fill search input with custom search query
                await target_frame.locator(search_input_selector).fill(search_query)
                self.logger.info(f"Filled search input with '{search_query}'")
                
                # Submit search
                if search_submit_selector:
                    await page.evaluate(f"document.querySelector({repr(search_submit_selector)}).click()")
                    self.logger.info("Clicked search submit button")
                else:
                    await target_frame.locator(search_input_selector).press('Enter')
                    self.logger.info("Pressed Enter to submit search")
            
            # Wait for results to load (both modes)
            await page.wait_for_load_state('networkidle', timeout=10000)
            await asyncio.sleep(3)  # Additional wait for dynamic content
            
            self.logger.info("Interaction completed successfully")
            
        except Exception as e:
            self.logger.error(f"Error performing search/button interaction: {str(e)}")
            # Continue with scraping even if interaction fails
    
    async def test_selectors(self, url: str, selectors: Dict) -> Dict:
        """
        Test selectors on a page to validate they work correctly.
        
        Args:
            url: URL to test
            selectors: Dictionary of selectors to test
            
        Returns:
            Dictionary with test results
        """
        if not self.browser:
            await self.start_browser()
        
        page = await self.context.new_page()
        
        try:
            try:
                await page.goto(url, wait_until='networkidle', timeout=30000)
            except Exception as e:
                self.logger.warning(f"Timeout after 30s while loading {url}. Proceeding with available page content.")
            
            results = {
                'url': url,
                'test_time': datetime.now().isoformat(),
                'results': {}
            }
            
            # Test each selector
            for selector_name, selector_value in selectors.items():
                if not selector_value:
                    continue
                    
                try:
                    elements = await page.query_selector_all(selector_value)
                    results['results'][selector_name] = {
                        'selector': selector_value,
                        'elements_found': len(elements),
                        'success': len(elements) > 0
                    }
                    
                    # Get sample text from first few elements
                    if elements:
                        sample_texts = []
                        for element in elements[:3]:
                            text = await element.text_content()
                            if text:
                                sample_texts.append(text.strip()[:100])
                        results['results'][selector_name]['sample_texts'] = sample_texts
                        
                except Exception as e:
                    results['results'][selector_name] = {
                        'selector': selector_value,
                        'error': str(e),
                        'success': False
                    }
            
            return results
            
        except Exception as e:
            return {
                'url': url,
                'test_time': datetime.now().isoformat(),
                'error': str(e),
                'success': False
            }
        finally:
            await page.close()

class PlaywrightScraperSync:
    """Synchronous wrapper for PlaywrightScraper for easier integration."""
    
    def __init__(self, use_database: bool = False):
        self.logger = logging.getLogger(__name__)
        self.use_database = use_database
        self.db_manager = None
        
        if self.use_database:
            try:
                from supabase_database import SupabaseDatabaseManager
                self.db_manager = SupabaseDatabaseManager()
                self.logger.info("Supabase database integration enabled")
            except ImportError:
                self.logger.warning("Database integration requested but SupabaseDatabaseManager not available")
                self.use_database = False
            except Exception as e:
                self.logger.error(f"Failed to initialize Supabase database: {e}")
                self.use_database = False
        
        # Initialize async scraper with database manager
        self.async_scraper = PlaywrightScraper(db_manager=self.db_manager)
    
    def scrape_jobs(self, url: str, scraper_config: Dict) -> Tuple[List[Dict], str]:
        """Synchronous wrapper for scraping jobs."""
        jobs, filtered_html = asyncio.run(self._async_scrape_jobs(url, scraper_config))
        
        # If database integration is enabled, synchronize results with Supabase
        if self.use_database and self.db_manager:
            company_name = scraper_config.get('company_name')
            if not company_name:
                self.logger.warning("No company_name in scraper config for database integration")
            else:
                company = self.db_manager.get_company_by_name(company_name)
                if not company:
                    self.logger.warning(f"Company '{company_name}' not found in database")
                else:
                    company_id = company['id']
                    active_urls = {job.get('url') for job in jobs if job.get('url')}

                    insertion_results = {'added': 0, 'duplicates': 0, 'errors': 0}
                    if jobs:
                        insertion_results = self.db_manager.add_jobs_batch(company_id, jobs)
                        self.logger.info(
                            "Database integration: %s jobs added, %s duplicates skipped, %s errors",
                            insertion_results['added'],
                            insertion_results['duplicates'],
                            insertion_results['errors']
                        )
                    else:
                        self.logger.info(f"No jobs scraped for '{company_name}'. Skipping insert step.")

                    cleanup_summary = self.db_manager.remove_stale_jobs(company_id, active_urls)
                    if cleanup_summary.get('error'):
                        self.logger.error(
                            "Stale cleanup failed for company %s: %s",
                            company_name,
                            cleanup_summary['error']
                        )
                    else:
                        self.logger.info(
                            "Stale cleanup results for '%s': %s removed, %s remain",
                            company_name,
                            cleanup_summary.get('removed', 0),
                            cleanup_summary.get('remaining', 0)
                        )

                    success = len(jobs) > 0 and insertion_results.get('errors', 0) == 0
                    error_message = None
                    if not jobs:
                        error_message = 'No jobs found during scrape'
                    elif insertion_results.get('errors'):
                        error_message = f"{insertion_results['errors']} errors while inserting jobs"

                    self.db_manager.log_scraper_execution(
                        company_id,
                        len(jobs),
                        success=success,
                        error_message=error_message
                    )
        
        return jobs, filtered_html
    
    async def _async_scrape_jobs(self, url: str, scraper_config: Dict) -> Tuple[List[Dict], str]:
        """Async implementation for scraping jobs."""
        async with self.async_scraper:
            return await self.async_scraper.scrape_jobs(url, scraper_config)
    
    def test_selectors(self, url: str, selectors: Dict) -> Dict:
        """Synchronous wrapper for testing selectors."""
        return asyncio.run(self._async_test_selectors(url, selectors))
    
    async def _async_test_selectors(self, url: str, selectors: Dict) -> Dict:
        """Async implementation for testing selectors."""
        async with self.async_scraper:
            return await self.async_scraper.test_selectors(url, selectors)
