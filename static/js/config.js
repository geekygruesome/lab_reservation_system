// API Configuration
// This file provides a centralized configuration for API endpoints
// Use relative paths so it works in any environment (localhost, production, etc.)

const API_CONFIG = {
    // Base URL for API endpoints - use relative path for portability
    BASE_URL: '',  // Empty string means relative to current domain
    
    // Helper function to build API URLs
    apiUrl: function(endpoint) {
        // Remove leading slash if present to avoid double slashes
        const cleanEndpoint = endpoint.startsWith('/') ? endpoint : '/' + endpoint;
        return this.BASE_URL + cleanEndpoint;
    }
};

// For backward compatibility, also export as window.API_BASE_URL
window.API_CONFIG = API_CONFIG;
window.API_BASE_URL = API_CONFIG.BASE_URL;

