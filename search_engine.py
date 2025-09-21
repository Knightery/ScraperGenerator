import requests
import json
import logging
from typing import List, Dict, Optional
from urllib.parse import urljoin, urlparse
from config import Config

class SearchEngine:
    """Handles company job board discovery using Brave Search API."""
    
    def __init__(self):
        self.api_key = Config.BRAVE_API_KEY
        self.base_url = "https://api.search.brave.com/res/v1/web/search"
        self.logger = logging.getLogger(__name__)
        
        if not self.api_key:
            raise ValueError("BRAVE_API_KEY not found in environment variables")
    
    def search_company_jobs(self, company_name: str, search_terms: List[str] = None) -> Optional[str]:
        """
        Search for a company's job board URL.
        
        Args:
            company_name: Name of the company to search for
            search_terms: Additional search terms (default: ['internship', 'careers'])
        
        Returns:
            URL of the company's job board or None if not found
        """
        if not search_terms:
            search_terms = Config.DEFAULT_SEARCH_TERMS
        
        for term in search_terms:
            query = f"{company_name} {term}"
            self.logger.info(f"Searching for: {query}")
            
            try:
                results = self._perform_search(query)
                job_board_url = self._extract_job_board_url(results, company_name)
                
                if job_board_url:
                    self.logger.info(f"Found job board for {company_name}: {job_board_url}")
                    return job_board_url
                    
            except Exception as e:
                self.logger.error(f"Search failed for {query}: {str(e)}")
                continue
        
        self.logger.warning(f"No job board found for {company_name}")
        return None
    
    def _perform_search(self, query: str) -> Dict:
        """Perform the actual search API call."""
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key
        }
        
        params = {
            "q": query,
            "result_filter": "web",
            "count": 10,
            "safesearch": "moderate"
        }
        
        response = requests.get(self.base_url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        
        return response.json()
    
    def _extract_job_board_url(self, search_results: Dict, company_name: str) -> Optional[str]:
        """
        Use DeepSeek AI to pick the best job board URL from search results.
        """
        if 'web' not in search_results or 'results' not in search_results['web']:
            return None
        
        results = search_results['web']['results'][:10]  # Only consider top 10 results
        
        if not results:
            return None
        
        # Use AI to select the best result
        selected_url = self._select_best_url_with_ai(results, company_name)
        
        if selected_url:
            self.logger.info(f"AI selected URL: {selected_url}")
            return selected_url
        
        # Fallback: return first result if AI selection fails
        fallback_url = results[0].get('url')
        self.logger.info(f"Using fallback URL: {fallback_url}")
        return fallback_url
    
    def _select_best_url_with_ai(self, results: List[Dict], company_name: str) -> Optional[str]:
        """Use DeepSeek AI to select the best URL for internship job listings."""
        try:
            # Import here to avoid circular imports
            import openai
            
            # Get DeepSeek API key from config
            from config import Config
            
            if not Config.DEEPSEEK_API_KEY:
                self.logger.warning("DEEPSEEK_API_KEY not found, falling back to first result")
                return results[0].get('url') if results else None
            
            # Configure OpenAI client for DeepSeek
            client = openai.OpenAI(
                api_key=Config.DEEPSEEK_API_KEY,
                base_url="https://api.deepseek.com/v1"
            )
            
            # Prepare search results for AI analysis
            results_text = ""
            for i, result in enumerate(results, 1):
                url = result.get('url', '')
                title = result.get('title', '')
                description = result.get('description', '')
                
                results_text += f"{i}. URL: {url}\n"
                results_text += f"   Title: {title}\n"
                results_text += f"   Description: {description}\n\n"
            
            system_prompt = f"""You are an expert at identifying the best job board URLs for internship listings.

Your task is to analyze search results and select the BEST URL that will lead to {company_name}'s internship job listings.

Prioritize URLs that:
1. Are from {company_name}'s official website (not third-party job sites)
2. Specifically mention internships, interns, students, or graduates
3. Lead directly to job listings (not general information pages)
4. Are likely to contain multiple internship postings

Avoid URLs from:
- LinkedIn, Indeed, Glassdoor, Monster, ZipRecruiter (third-party sites)
- General company information pages
- Blog posts or news articles
- Social media pages

Return ONLY the number (1-{len(results)}) of the best result. If none are suitable, return "0"."""

            user_prompt = f"""Select the best URL for finding {company_name} internship job listings:

{results_text}

Return only the number of the best result (1-{len(results)}) or "0" if none are suitable."""

            response = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=10
            )
            
            response_text = response.choices[0].message.content.strip()
            
            # Parse the response
            try:
                selection = int(response_text)
                if 1 <= selection <= len(results):
                    selected_result = results[selection - 1]
                    selected_url = selected_result.get('url')
                    self.logger.info(f"AI selected result #{selection}: {selected_url}")
                    self.logger.info(f"Selected title: {selected_result.get('title', 'N/A')}")
                    return selected_url
                elif selection == 0:
                    self.logger.warning("AI determined no results are suitable")
                    return None
                else:
                    self.logger.warning(f"AI returned invalid selection: {selection}")
                    return None
            except ValueError:
                self.logger.warning(f"AI returned non-numeric response: {response_text}")
                return None
                
        except Exception as e:
            self.logger.error(f"AI URL selection failed: {str(e)}")
            return None
    
    def validate_job_board_url(self, url: str) -> bool:
        """
        Validate that a URL is accessible and likely contains job listings.
        """
        try:
            response = requests.head(url, timeout=10, allow_redirects=True)
            if response.status_code == 200:
                # Could add more sophisticated validation here
                return True
        except Exception as e:
            self.logger.warning(f"URL validation failed for {url}: {str(e)}")
        
        return False
