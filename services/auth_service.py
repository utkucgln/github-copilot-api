"""
Authentication Service - Simple API key validation.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AuthService:
    """
    Simple authentication service for API key validation.
    """
    
    def __init__(self):
        """Initialize the auth service."""
        self._api_key = os.getenv("API_KEY", "")
    
    def validate_token(self, auth_header: Optional[str]) -> bool:
        """
        Validate the authorization header.
        
        Args:
            auth_header: The Authorization header value
            
        Returns:
            True if valid, False otherwise
        """
        # If no API key is configured, allow all requests (dev mode)
        if not self._api_key:
            logger.warning("No API_KEY configured - allowing unauthenticated access")
            return True
        
        if not auth_header:
            return False
        
        # Check for Bearer token
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            return token == self._api_key
        
        # Check for ApiKey prefix
        if auth_header.startswith("ApiKey "):
            key = auth_header[7:]
            return key == self._api_key
        
        # Direct comparison
        return auth_header == self._api_key
