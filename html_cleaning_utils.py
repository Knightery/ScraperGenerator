#!/usr/bin/env python3
"""
Shared HTML cleaning utilities for pagination preservation.
Used by ai_navigator.py, playwright_scraper.py, and Archive/clean_html_tool.py
"""

from bs4 import BeautifulSoup, Comment

def contains_pagination(element):
    """Check if element contains the word 'pagination' anywhere in its HTML."""
    if element is None:
        return False
    # Check if element has a None name (happens with decomposed/invalid elements)
    if not hasattr(element, 'name') or element.name is None:
        return False
    try:
        return 'pagination' in str(element).lower()
    except (TypeError, AttributeError):
        # Handle cases where element can't be converted to string
        return False


def clean_non_pagination_children(element):
    """Remove children that don't contain pagination, but preserve the parent structure."""
    children_to_remove = []
    
    # Check direct children
    for child in element.find_all(recursive=False):
        # Skip if child is already invalid/decomposed
        if not hasattr(child, 'name') or child.name is None:
            continue
        if not contains_pagination(child):
            # Check if this child is part of pagination structure (common pagination elements)
            is_pagination_related = False
            
            # Check if child has pagination-related classes, roles, or contains pagination links
            child_classes = ' '.join(child.get('class', [])).lower()
            child_role = child.get('role', '').lower()
            child_aria_label = child.get('aria-label', '').lower()
            
            # Common pagination element patterns
            pagination_indicators = [
                'page', 'next', 'prev', 'previous', 'first', 'last', 
                'navigation', 'nav-item', 'nav-link'
            ]
            
            # Check if child has pagination indicators
            if (any(indicator in child_classes for indicator in pagination_indicators) or
                any(indicator in child_role for indicator in pagination_indicators) or
                any(indicator in child_aria_label for indicator in pagination_indicators)):
                is_pagination_related = True
            
            # Check if child contains links that look like pagination
            pagination_links = child.find_all('a', href=lambda x: x and ('page=' in x or x in ['#', '']))
            if pagination_links:
                is_pagination_related = True
            
            # Check if child contains text that indicates pagination
            child_text = child.get_text().lower()
            pagination_text_indicators = ['next', 'prev', 'previous', 'first', 'last']
            if any(indicator in child_text for indicator in pagination_text_indicators):
                # Only consider it pagination if it's short text (likely a button/link)
                if len(child_text.strip()) < 20:
                    is_pagination_related = True
            
            # Check if child contains numbered links (1, 2, 3, etc.) or pagination hrefs
            numbered_links = child.find_all('a', string=lambda text: text and text.strip().isdigit())
            page_links = child.find_all('a', href=lambda x: x and 'page=' in x)
            if numbered_links or page_links:
                is_pagination_related = True
            
            if not is_pagination_related:
                children_to_remove.append(child)
            else:
                # This child is pagination-related, recursively clean its children
                clean_non_pagination_children(child)
        else:
            # If child has pagination, recursively clean its children too
            clean_non_pagination_children(child)
    
    # Remove children that don't have pagination
    for child in children_to_remove:
        if hasattr(child, 'extract'):
            child.extract()


def clean_irrelevant_tags_with_pagination_preservation(soup, irrelevant_tags, logger=None):
    """
    Remove irrelevant HTML tags while preserving elements containing pagination.
    
    Args:
        soup: BeautifulSoup object
        irrelevant_tags: List of tag names to remove
        logger: Optional logger for debug messages
    """
    for tag_name in irrelevant_tags:
        for element in soup.find_all(tag_name):
            # Skip if element is already invalid
            if not hasattr(element, 'name') or element.name is None:
                continue
            if not contains_pagination(element):
                element.extract()
            else:
                if logger:
                    logger.debug(f"Preserving <{tag_name}> tag because it contains pagination, cleaning non-pagination children")
                else:
                    print(f"Preserving <{tag_name}> tag because it contains pagination, cleaning non-pagination children")
                # Keep the parent but clean out non-pagination children
                clean_non_pagination_children(element)


def clean_irrelevant_selectors_with_pagination_preservation(soup, irrelevant_selectors, logger=None):
    """
    Remove elements matching CSS selectors while preserving elements containing pagination.
    
    Args:
        soup: BeautifulSoup object
        irrelevant_selectors: List of CSS selectors to remove
        logger: Optional logger for debug messages
    """
    for selector in irrelevant_selectors:
        for element in soup.select(selector):
            # Skip if element is already invalid
            if not hasattr(element, 'name') or element.name is None:
                continue
            if not contains_pagination(element):
                element.extract()
            else:
                if logger:
                    logger.debug(f"Preserving element matching '{selector}' because it contains pagination, cleaning non-pagination children")
                else:
                    print(f"Preserving element matching '{selector}' because it contains pagination, cleaning non-pagination children")
                # Keep the parent but clean out non-pagination children
                clean_non_pagination_children(element)


def strip_whitespace_and_empty_lines(html_content: str) -> str:
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
        print(f"Error stripping whitespace: {str(e)}")
        return html_content


def get_standard_irrelevant_tags():
    """Get the standard list of irrelevant HTML tags to remove."""
    return [
        # Original list
        'script', 'style', 'meta', 'link', 'noscript',
        'header', 'footer', 'nav', 'aside',
        
        # Newly added tags
        'svg', 'dialog', 'template',
        'canvas', 'audio', 'video'
    ]


def get_standard_irrelevant_selectors():
    """Get the standard list of irrelevant CSS selectors to remove."""
    return [
        # Navigation and headers
        '.header', '.footer', '.navbar', '.menu',
        '.breadcrumb', '.breadcrumbs', '.sidebar', '.aside',
        '#header', '#footer', '#navbar', '#menu',
        
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


def clean_html_content_comprehensive(html_content: str, logger=None) -> str:
    """
    Comprehensive HTML cleaning function that removes irrelevant sections while preserving pagination.
    
    Args:
        html_content: Raw HTML content to clean
        logger: Optional logger for debug messages
        
    Returns:
        Cleaned HTML content as string
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove all HTML comments (notes)
        comments = soup.find_all(string=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment.extract()
        
        # Get standard lists
        irrelevant_tags = get_standard_irrelevant_tags()
        irrelevant_selectors = get_standard_irrelevant_selectors()
        
        # Clean irrelevant tags while preserving pagination elements
        clean_irrelevant_tags_with_pagination_preservation(soup, irrelevant_tags, logger)
        
        # Clean irrelevant selectors while preserving pagination elements  
        clean_irrelevant_selectors_with_pagination_preservation(soup, irrelevant_selectors, logger)
        
        # Only truncate raw text nodes in divs, preserve links and structure
        for div in soup.find_all('div'):
            # Only process divs that have direct text content (not just nested elements)
            if div.string and len(div.string.strip()) > 100:
                # Only truncate if this div contains just text, no nested elements like links
                div.string.replace_with(div.string[:100] + "... [TRUNCATED]")
        
        # Apply whitespace stripping and empty line removal to HTML
        cleaned_html_str = strip_whitespace_and_empty_lines(str(soup))
        
        return cleaned_html_str
        
    except Exception as e:
        if logger:
            logger.warning(f"Error cleaning HTML content: {type(e).__name__}: {str(e)}")
        else:
            print(f"Error cleaning HTML content: {type(e).__name__}: {str(e)}")
        return html_content
