import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    # API Keys
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
    BRAVE_API_KEY = os.getenv('BRAVE_API_KEY')
    
    # Database Configuration
    DATABASE_PATH = os.getenv('DATABASE_PATH', './jobs.db')
    
    # Logging Configuration
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # Scraping Configuration
    SCRAPING_INTERVAL = int(os.getenv('SCRAPING_INTERVAL', 3600))
    MAX_CONCURRENT_SCRAPERS = int(os.getenv('MAX_CONCURRENT_SCRAPERS', 5))
    DOWNLOAD_DELAY = float(os.getenv('DOWNLOAD_DELAY', 2))
    RANDOMIZE_DOWNLOAD_DELAY = float(os.getenv('RANDOMIZE_DOWNLOAD_DELAY', 0.5))
    
    # AI Configuration
    AI_RETRY_ATTEMPTS = int(os.getenv('AI_RETRY_ATTEMPTS', 3))
    SCRAPER_VALIDATION_THRESHOLD = float(os.getenv('SCRAPER_VALIDATION_THRESHOLD', 0.8))
    
    # Search Configuration
    DEFAULT_SEARCH_TERMS = os.getenv('DEFAULT_SEARCH_TERMS', 'student summer internship,careers,jobs').split(',')
    
    # Scrapy Settings
    SCRAPY_SETTINGS = {
        'ROBOTSTXT_OBEY': True,
        'DOWNLOAD_DELAY': DOWNLOAD_DELAY,
        'RANDOMIZE_DOWNLOAD_DELAY': RANDOMIZE_DOWNLOAD_DELAY,
        'CONCURRENT_REQUESTS': 16,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 8,
        'USER_AGENT': 'dynamic_scraper (+http://www.yourdomain.com)',
        'AUTOTHROTTLE_ENABLED': True,
        'AUTOTHROTTLE_START_DELAY': 1,
        'AUTOTHROTTLE_MAX_DELAY': 60,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 1.0,
        'AUTOTHROTTLE_DEBUG': False,
    }
