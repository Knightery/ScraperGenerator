# Copilot Instructions for ScraperGenerator
Never make summary documents to explain your changes.

## Core architecture
- Primary workflow lives in `main_scraper.py`: `SearchEngine` → `AINavigator` → `PlaywrightScraperSync` → `SupabaseDatabaseManager`.
- `SearchEngine` (Brave + Gemini) ranks job-board URLs; it requires `BRAVE_API_KEY` and `GEMINI_API_KEY` env vars.
- `AINavigator` navigates pages with synchronous Playwright, cleans HTML via `html_cleaning_utils.clean_html_content_comprehensive`, and produces CSS selectors plus optional search/button actions.
- `PlaywrightScraper` (async) executes the generated config: handles overlays, optional search interaction, regex keyword filtering via `text_filter_keywords`, and pagination with duplicate URL checks.
- Generated scripts reuse `scraper_template.py`; filenames follow `{company}_scraper.py` inside `scrapers/` and assume Supabase persistence.

## Environment expectations
- Copy `example_env.txt`, then provide Supabase creds (`SUPABASE_URL`, `SUPABASE_ANON_KEY`) alongside Brave/Gemini keys before running anything.
- After installing `requirements.txt`, run `python -m playwright install firefox` to match the hard-coded Firefox launch.
- Supabase setup expects an `exec_sql` RPC for table creation; without it, call `SupabaseDatabaseManager.create_tables_if_not_exist()` manually.

## Working with the scraper pipeline
- Use `python scrape_cli.py test-workflow "Company"` for a full dry run (search → selector validation → sample scrape → file generation).
- Adding a company via CLI (`python scrape_cli.py add "Company"`) stores script text in Supabase and writes a standalone scraper into `scrapers/`.
- `CompanyJobScraper.scrape_company` runs the generated script in a subprocess and reads jobs back from Supabase using `SupabaseDatabaseManager.get_jobs_by_company`.
- When adjusting selector logic, keep `PlaywrightScraper._extract_job_data` contract: return dicts with `title` and absolute `url`, or the job is dropped.
- Pagination is guarded by duplicate detection across current run + existing DB URLs; changing selector noise can stop pagination (duplicate ratio ≥ 50% ends the loop).

## Patterns & conventions
- Always normalize whitespace with `clean_extracted_text` before storing fields; new extraction code should mirror that helper.
- Search interactions support two mutually exclusive modes: (1) button-only via `search_submit_selector`, (2) typed query using `search_input_selector` + `search_query`; keep configs consistent with these booleans.
- `text_filter_keywords` is a comma list interpreted as case-insensitive substrings joined with `|`; avoid regex tokens in the keywords themselves.
- Logging defaults to file + stdout; respect existing handlers instead of reinitializing logging globally.
- Generated scripts assume Supabase; legacy SQLite helpers under `Archive/` are examples only—avoid reviving `DatabaseManager` unless migrating intentionally.

## Web interface & deployment
- Flask UI lives under `api/`; run `python api/main.py` locally or `npm run dev` (wraps the same command). `vercel.json` routes `/` traffic to that entry point.
- Frontend templates in `templates/` expect DB rows with `company_name`, `scraped_at`, etc.—keep new fields backward-compatible or update templates.
- For Vercel, trim dependencies to `requirements-vercel.txt` and ensure `DATABASE_URL` points to a managed Postgres variant; local SQLite is read-only in serverless contexts.

## Known gaps
- `auto_scraper.py` still references a removed `DatabaseManager`; treat it as legacy scaffolding until it’s refactored onto Supabase APIs.
- `api/main.py` contains residual SQLite `get_connection()` usage—update to Supabase helpers before extending those routes.
