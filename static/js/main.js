// Main JavaScript for Job Scraper Web Interface

document.addEventListener('DOMContentLoaded', function() {
    // Initialize all components
    initializeClock();
    initializeSearch();
    initializeAnimations();
    initializeTooltips();
    initializeLocalStorage();
    
    console.log('Job Scraper Web Interface initialized');
});

// Real-time clock in navigation
function initializeClock() {
    const clockElement = document.getElementById('current-time');
    if (!clockElement) return;
    
    function updateClock() {
        const now = new Date();
        const timeString = now.toLocaleTimeString('en-US', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit'
        });
        clockElement.textContent = timeString;
    }
    
    updateClock();
    setInterval(updateClock, 1000);
}

// Enhanced search functionality
function initializeSearch() {
    const searchForm = document.getElementById('job-search-form');
    const searchInput = document.getElementById('search');
    const companySelect = document.getElementById('company');
    const locationSelect = document.getElementById('location');
    
    if (!searchForm) return;
    
    // Debounced search for better UX
    let searchTimeout;
    
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                if (this.value.length >= 3 || this.value.length === 0) {
                    performLiveSearch();
                }
            }, 500);
        });
        
        // Clear search button
        const clearButton = createClearButton(searchInput);
        searchInput.parentNode.style.position = 'relative';
        searchInput.parentNode.appendChild(clearButton);
    }
    
    // Auto-submit on filter changes
    [companySelect, locationSelect].forEach(select => {
        if (select) {
            select.addEventListener('change', function() {
                showLoadingState();
                searchForm.submit();
            });
        }
    });
    
    // Save search state to localStorage
    if (searchInput) {
        searchInput.addEventListener('input', () => saveSearchState());
    }
    
    // Restore search state
    restoreSearchState();
}

// Create clear button for search input
function createClearButton(input) {
    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.className = 'btn btn-link position-absolute';
    clearBtn.style.cssText = 'right: 10px; top: 50%; transform: translateY(-50%); z-index: 10; padding: 0; border: none;';
    clearBtn.innerHTML = '<i class="bi bi-x-circle-fill text-muted"></i>';
    clearBtn.title = 'Clear search';
    
    clearBtn.addEventListener('click', function() {
        input.value = '';
        input.focus();
        if (document.getElementById('job-search-form')) {
            document.getElementById('job-search-form').submit();
        }
    });
    
    // Show/hide based on input content
    function toggleClearButton() {
        clearBtn.style.display = input.value ? 'block' : 'none';
    }
    
    input.addEventListener('input', toggleClearButton);
    toggleClearButton();
    
    return clearBtn;
}

// Live search functionality (optional enhancement)
function performLiveSearch() {
    const searchInput = document.getElementById('search');
    const companySelect = document.getElementById('company');
    const locationSelect = document.getElementById('location');
    
    if (!searchInput) return;
    
    const params = new URLSearchParams({
        q: searchInput.value,
        company: companySelect ? companySelect.value : '',
        location: locationSelect ? locationSelect.value : '',
        limit: 20
    });
    
    // Show loading indicator
    showSearchLoading();
    
    fetch(`/api/jobs/search?${params}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateSearchResults(data.jobs);
            } else {
                console.error('Search failed:', data.error);
            }
        })
        .catch(error => {
            console.error('Search error:', error);
        })
        .finally(() => {
            hideSearchLoading();
        });
}

// Update search results dynamically
function updateSearchResults(jobs) {
    const container = document.getElementById('jobs-container');
    if (!container) return;
    
    if (jobs.length === 0) {
        container.innerHTML = `
            <div class="col-12">
                <div class="alert alert-info text-center">
                    <i class="bi bi-info-circle me-2"></i>
                    No jobs found matching your criteria.
                </div>
            </div>
        `;
        return;
    }
    
    container.innerHTML = jobs.map(job => createJobCard(job)).join('');
    initializeAnimations(); // Re-initialize animations for new content
}

// Create job card HTML
function createJobCard(job) {
    const description = job.description ? 
        `<p class="card-text job-description">
            ${job.description.substring(0, 300)}${job.description.length > 300 ? '...' : ''}
        </p>` : '';
    
    const location = job.location ? 
        `<p class="text-muted mb-2">
            <i class="bi bi-geo-alt me-1"></i>${job.location}
        </p>` : '';
    
    const postedDate = job.posted_date ? 
        `<small class="text-muted d-block">
            <i class="bi bi-clock me-1"></i>Posted: ${job.posted_date}
        </small>` : '';
    
    return `
        <div class="col-12 mb-4">
            <div class="card job-card">
                <div class="card-body">
                    <div class="row">
                        <div class="col-md-8">
                            <div class="d-flex justify-content-between align-items-start mb-2">
                                <h5 class="card-title mb-0">
                                    <a href="${job.url}" target="_blank" class="text-decoration-none job-title">
                                        ${job.title}
                                    </a>
                                </h5>
                                <span class="badge bg-primary ms-2">${job.company_name}</span>
                            </div>
                            ${location}
                            ${description}
                        </div>
                        <div class="col-md-4 text-md-end">
                            <div class="mb-3">
                                <small class="text-muted d-block">
                                    <i class="bi bi-calendar3 me-1"></i>
                                    Scraped: ${job.scraped_at.substring(0, 10)}
                                </small>
                                ${postedDate}
                            </div>
                            <a href="${job.url}" target="_blank" class="btn btn-outline-primary">
                                View Job <i class="bi bi-external-link ms-1"></i>
                            </a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

// Loading states
function showLoadingState() {
    const container = document.getElementById('jobs-container');
    if (container) {
        container.innerHTML = `
            <div class="col-12 text-center py-5">
                <div class="loading"></div>
                <p class="mt-3 text-muted">Loading jobs...</p>
            </div>
        `;
    }
}

function showSearchLoading() {
    const searchBtn = document.querySelector('#job-search-form button[type="submit"]');
    if (searchBtn) {
        searchBtn.innerHTML = '<div class="loading me-2"></div>Searching...';
        searchBtn.disabled = true;
    }
}

function hideSearchLoading() {
    const searchBtn = document.querySelector('#job-search-form button[type="submit"]');
    if (searchBtn) {
        searchBtn.innerHTML = '<i class="bi bi-search me-1"></i>Search';
        searchBtn.disabled = false;
    }
}

// Animation initialization
function initializeAnimations() {
    // Intersection Observer for scroll animations
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, {
        threshold: 0.1,
        rootMargin: '0px 0px -50px 0px'
    });
    
    // Observe all cards
    document.querySelectorAll('.card').forEach(card => {
        observer.observe(card);
    });
    
    // Add hover effects to job cards
    document.querySelectorAll('.job-card').forEach(card => {
        card.addEventListener('mouseenter', function() {
            this.style.transform = 'translateY(-2px)';
        });
        
        card.addEventListener('mouseleave', function() {
            this.style.transform = 'translateY(0)';
        });
    });
}

// Initialize Bootstrap tooltips
function initializeTooltips() {
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });
}

// Local storage functions
function initializeLocalStorage() {
    // Clear old localStorage entries older than 7 days
    const oneWeek = 7 * 24 * 60 * 60 * 1000;
    const now = Date.now();
    
    Object.keys(localStorage).forEach(key => {
        if (key.startsWith('jobscraper_')) {
            try {
                const data = JSON.parse(localStorage.getItem(key));
                if (data.timestamp && (now - data.timestamp) > oneWeek) {
                    localStorage.removeItem(key);
                }
            } catch (e) {
                localStorage.removeItem(key);
            }
        }
    });
}

function saveSearchState() {
    const searchInput = document.getElementById('search');
    const companySelect = document.getElementById('company');
    const locationSelect = document.getElementById('location');
    
    if (searchInput) {
        const state = {
            search: searchInput.value,
            company: companySelect ? companySelect.value : '',
            location: locationSelect ? locationSelect.value : '',
            timestamp: Date.now()
        };
        
        localStorage.setItem('jobscraper_search_state', JSON.stringify(state));
    }
}

function restoreSearchState() {
    try {
        const saved = localStorage.getItem('jobscraper_search_state');
        if (!saved) return;
        
        const state = JSON.parse(saved);
        const oneHour = 60 * 60 * 1000;
        
        // Only restore if less than 1 hour old
        if (Date.now() - state.timestamp > oneHour) {
            localStorage.removeItem('jobscraper_search_state');
            return;
        }
        
        const searchInput = document.getElementById('search');
        const companySelect = document.getElementById('company');
        const locationSelect = document.getElementById('location');
        
        if (searchInput && !searchInput.value) searchInput.value = state.search || '';
        if (companySelect && !companySelect.value) companySelect.value = state.company || '';
        if (locationSelect && !locationSelect.value) locationSelect.value = state.location || '';
        
    } catch (e) {
        localStorage.removeItem('jobscraper_search_state');
    }
}

// Statistics updating
function updateStatsRealTime() {
    fetch('/api/stats')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                const stats = data.stats;
                
                // Update stat numbers with animation
                updateStatNumber('total_jobs', stats.total_jobs);
                updateStatNumber('total_companies', stats.total_companies);
                updateStatNumber('jobs_this_week', stats.jobs_this_week);
                updateStatNumber('jobs_today', stats.jobs_today);
            }
        })
        .catch(error => {
            console.error('Failed to update stats:', error);
        });
}

function updateStatNumber(elementId, newValue) {
    const elements = document.querySelectorAll(`[data-stat="${elementId}"], .stat-${elementId}`);
    elements.forEach(element => {
        const currentValue = parseInt(element.textContent.replace(/,/g, ''));
        if (currentValue !== newValue) {
            animateNumber(element, currentValue, newValue);
        }
    });
}

function animateNumber(element, start, end) {
    const duration = 1000;
    const stepTime = 50;
    const steps = duration / stepTime;
    const increment = (end - start) / steps;
    let current = start;
    
    const timer = setInterval(() => {
        current += increment;
        if ((increment > 0 && current >= end) || (increment < 0 && current <= end)) {
            current = end;
            clearInterval(timer);
        }
        element.textContent = Math.floor(current).toLocaleString();
    }, stepTime);
}

// Utility functions
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

function formatRelativeTime(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    
    if (diffDays === 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return `${diffDays} days ago`;
    if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
    return formatDate(dateString);
}

// Copy to clipboard functionality
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast('Copied to clipboard!', 'success');
    }).catch(() => {
        // Fallback for older browsers
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast('Copied to clipboard!', 'success');
    });
}

// Toast notifications
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast align-items-center text-white bg-${type} border-0`;
    toast.setAttribute('role', 'alert');
    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body">${message}</div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
        </div>
    `;
    
    // Create toast container if it doesn't exist
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed bottom-0 end-0 p-3';
        document.body.appendChild(container);
    }
    
    container.appendChild(toast);
    
    const bsToast = new bootstrap.Toast(toast);
    bsToast.show();
    
    toast.addEventListener('hidden.bs.toast', () => {
        toast.remove();
    });
}

// Auto-refresh functionality for stats (every 5 minutes)
setInterval(() => {
    if (window.location.pathname === '/') {
        updateStatsRealTime();
    }
}, 5 * 60 * 1000);

// Export functions for global use
window.JobScraper = {
    updateStatsRealTime,
    showToast,
    copyToClipboard,
    formatDate,
    formatRelativeTime
};