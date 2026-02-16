"""
Services package for GitHub Copilot API.
"""

from .copilot_service import CopilotService
from .auth_service import AuthService

__all__ = ["CopilotService", "AuthService"]
