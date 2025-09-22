How does it work:

SEARCH:

1. Uses Brave API in order to search for a relevant link

SCRAPING:
2. Uses playwright with viewport 1920 height 1080 and user_agent Firefox
3. Uses beautifulsoup in order to cut out useless information such as header and footer.
4. On the relevant link, sees if we should STAY or LEAVE to find job listings, feeds all links containing specific words on that page into LLM to choose whether or not to leave
5. Goes to the job board, then takes the ENTIRE RELEVANT HTML and feeds it to the LLM in order to understand the structure of jobs.
6. Parses this html to create a specific scraper script that will go to the job board URL, scrape every single job on the site using the specific indicators. The LLM should create the scraper script.
7. Test the scraper, see if any jobs are retrieved. Use LLM to evaluate if jobs were retrieved or not.
8. If so - Good, if not - Retry the script, feeding it the error logs. Do this up to two times. Make sure that everything is LLM friendly and industry standard.
9. Save the final scraper in the current directory.

DB:
10. When the scraper runs, jobs go to jobs.db sorted by the url to ensure no repeats
Todo: Merge entries where only field such as location is different, while the time is still the same.
Todo:r Standardize things like location

AUTOUPDATE (not implemented yet):
11. Run the scraping script once every hour

FRONTEND (not implemented yet):
12. User can type in anything and then see what happens

TODO: Cinnamon Roll, fix searching by allowing interaction with the search bar

IMPROVEMENT NECESSARY: MAKE IT SO WE CAN SEE PAGINATION, IT IS AT BOTTOM SO SOMETIMES IS TRUNCATED - MOSTLY FIXED, one method could be feeding in the entire first html and letting the bot say which tags are irrelevant to then be able to see more at the bottom
