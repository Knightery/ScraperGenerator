## Interactive scraper builder

Visit `http://localhost:5000/create-scraper` (or `/create-scraper` on your deployment) to launch a guided workflow that mirrors `python scrape_cli.py add "Company"`.

Bring your own **Gemini API key** when starting a run – the UI will prompt for it and only uses the key for that single workflow. The live dashboard shows:

* Real-time status pills that track search, analysis, validation, generation, and storage stages
* A miniature browser window streaming Playwright screenshots from the AI navigator
* A structured log timeline with timestamps and status chips
* Final output details, including the generated scraper path and resolved job board URL

## Pipeline overview

### Search
1. Uses the Brave API to surface candidate job boards
2. Gemini ranks the results to pick the best internship portal

### Scraping
3. Playwright launches a Firefox session with a 1920×1080 viewport
4. HTML is cleaned with BeautifulSoup to remove chrome and extract link graph
5. The AI navigator determines whether to stay, drill deeper, or return to search results
6. Cleaned HTML and interactions are fed to Gemini to synthesize CSS selectors
7. Playwright tests the selectors, scraping a sample of internship postings
8. Gemini reviews the sample for correctness; on failure the loop retries up to two times
9. A standalone scraper script is generated and saved locally

### Database
10. Jobs are persisted to Supabase with de-duplication by URL
11. Legacy SQLite support (`jobs.db`) remains for local experimentation

## Backlog
* Merge job entries where only location differs while timestamps match
* Standardize location and compensation fields
* Autoupdate pipeline for hourly scraping runs
* Enhanced search bar interactions for tricky sites
