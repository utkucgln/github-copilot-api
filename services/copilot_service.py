"""
GitHub Copilot Service - Interfaces with GitHub Copilot CLI.

This service wraps the new GitHub Copilot CLI (copilot) 
to expose chat capabilities as a REST API.

Each request creates a temporary workspace where Copilot can:
- Create files
- Edit code
- Execute actions

The response includes all files created/modified as base64.

Requirements:
- GitHub Copilot CLI installed: winget install GitHub.Copilot (Windows)
                                brew install copilot-cli (macOS/Linux)
                                npm install -g @github/copilot
- Authenticated with GH_TOKEN or GITHUB_TOKEN environment variable
  (Create a fine-grained PAT with "Copilot Requests" permission)
"""

import os
import json
import logging
import asyncio
import re
import time
import tempfile
import shutil
import base64
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class CopilotService:
    """
    Service for interacting with GitHub Copilot via the new Copilot CLI.
    
    Uses 'copilot -p' for non-interactive prompts.
    
    Authentication:
    - Set GH_TOKEN or GITHUB_TOKEN environment variable with a GitHub PAT 
      that has 'Copilot Requests' permission (fine-grained PAT)
    - Create token at: https://github.com/settings/personal-access-tokens/new
    """
    
    def __init__(self):
        """Initialize the Copilot service."""
        self._copilot_path = os.getenv("COPILOT_PATH", "copilot")
        self._gh_token = os.getenv("GH_TOKEN", "") or os.getenv("GITHUB_TOKEN", "")
        self._default_model = os.getenv("COPILOT_MODEL", "claude-sonnet-4")
        
    def _get_env(self) -> Dict[str, str]:
        """Get environment variables for Copilot CLI, including auth token."""
        env = os.environ.copy()
        if self._gh_token:
            env["GH_TOKEN"] = self._gh_token
            env["GITHUB_TOKEN"] = self._gh_token
        return env
    
    def _create_temp_workspace(self) -> str:
        """Create a temporary workspace directory for this request."""
        workspace_id = str(uuid.uuid4())[:8]
        workspace_path = os.path.join(tempfile.gettempdir(), f"copilot_workspace_{workspace_id}")
        os.makedirs(workspace_path, exist_ok=True)
        logger.info(f"Created temp workspace: {workspace_path}")
        return workspace_path
    
    def _cleanup_workspace(self, workspace_path: str):
        """Clean up the temporary workspace."""
        try:
            if os.path.exists(workspace_path):
                shutil.rmtree(workspace_path)
                logger.info(f"Cleaned up workspace: {workspace_path}")
        except Exception as e:
            logger.warning(f"Failed to cleanup workspace {workspace_path}: {e}")
    
    def _scan_workspace_files(self, workspace_path: str) -> List[Dict[str, Any]]:
        """
        Scan workspace for all files and return them with base64 content.
        Ignores virtual environments, cache files, and other common artifacts.
        
        Returns:
            List of file info dicts with path, content (base64), size, etc.
        """
        # Directories and patterns to ignore
        IGNORED_DIRS = {
            '.venv', 'venv', 'env', '.env',  # Virtual environments
            '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache',  # Python caches
            'node_modules', '.npm',  # Node.js
            '.git', '.svn', '.hg',  # Version control
            '.idea', '.vscode', '.vs',  # IDE folders
            'dist', 'build', 'target', 'out',  # Build outputs
            '.tox', '.nox', 'htmlcov', '.coverage',  # Testing
            'egg-info', '.eggs',  # Python packaging
        }
        
        IGNORED_EXTENSIONS = {
            '.pyc', '.pyo', '.pyd',  # Python compiled
            '.so', '.dll', '.dylib',  # Compiled libraries
            '.exe', '.bin',  # Executables
            '.log', '.tmp', '.temp',  # Temp/log files
            '.DS_Store', '.gitignore', '.gitattributes',  # System/git files
        }
        
        IGNORED_FILES = {
            '.DS_Store', 'Thumbs.db', 'desktop.ini',  # OS files
            '.env', '.env.local', '.env.development',  # Environment files (might contain secrets)
        }
        
        files = []
        workspace = Path(workspace_path)
        
        for file_path in workspace.rglob("*"):
            if file_path.is_file():
                # Check if any parent directory is in ignored list
                relative_path = file_path.relative_to(workspace)
                path_parts = relative_path.parts
                
                # Skip if any directory in path is ignored
                if any(part in IGNORED_DIRS for part in path_parts[:-1]):
                    continue
                
                # Skip if file extension is ignored
                if file_path.suffix.lower() in IGNORED_EXTENSIONS:
                    continue
                
                # Skip if filename is in ignored list
                if file_path.name in IGNORED_FILES:
                    continue
                
                # Skip hidden files (starting with .)
                if file_path.name.startswith('.') and file_path.name not in {'.gitignore', '.dockerignore'}:
                    continue
                
                try:
                    file_size = file_path.stat().st_size
                    
                    # Skip very large files (> 1MB)
                    if file_size > 1024 * 1024:
                        logger.warning(f"Skipping large file: {relative_path} ({file_size} bytes)")
                        continue
                    
                    # Read content and encode as base64
                    with open(file_path, "rb") as f:
                        content_bytes = f.read()
                    
                    # Try to decode as text first
                    try:
                        content_text = content_bytes.decode("utf-8")
                        is_binary = False
                    except UnicodeDecodeError:
                        content_text = None
                        is_binary = True
                    
                    content_base64 = base64.b64encode(content_bytes).decode("ascii")
                    
                    # Detect file type
                    extension = file_path.suffix.lower()
                    mime_type = self._get_mime_type(extension)
                    
                    files.append({
                        "path": str(relative_path).replace("\\", "/"),
                        "name": file_path.name,
                        "extension": extension,
                        "size": file_size,
                        "is_binary": is_binary,
                        "mime_type": mime_type,
                        "content_base64": content_base64,
                        "content_text": content_text if not is_binary else None
                    })
                    
                except Exception as e:
                    logger.warning(f"Failed to read file {file_path}: {e}")
        
        return files
    
    def _get_mime_type(self, extension: str) -> str:
        """Get MIME type from file extension."""
        mime_map = {
            ".py": "text/x-python",
            ".js": "text/javascript",
            ".ts": "text/typescript",
            ".jsx": "text/jsx",
            ".tsx": "text/tsx",
            ".json": "application/json",
            ".html": "text/html",
            ".css": "text/css",
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".yaml": "text/yaml",
            ".yml": "text/yaml",
            ".xml": "application/xml",
            ".sh": "text/x-shellscript",
            ".bash": "text/x-shellscript",
            ".ps1": "text/x-powershell",
            ".java": "text/x-java",
            ".c": "text/x-c",
            ".cpp": "text/x-c++",
            ".h": "text/x-c",
            ".cs": "text/x-csharp",
            ".go": "text/x-go",
            ".rs": "text/x-rust",
            ".rb": "text/x-ruby",
            ".php": "text/x-php",
            ".sql": "text/x-sql",
            ".dockerfile": "text/x-dockerfile",
            ".gitignore": "text/plain",
            ".env": "text/plain",
        }
        return mime_map.get(extension, "application/octet-stream")
        
    async def _run_copilot_command(
        self, 
        prompt: str, 
        model: Optional[str] = None,
        silent: bool = True,
        workspace_path: Optional[str] = None
    ) -> tuple[str, str, int]:
        """
        Run a copilot command asynchronously using non-interactive mode.
        
        Args:
            prompt: The prompt to send to Copilot
            model: Model to use (claude-sonnet-4, gpt-5, etc.)
            silent: Whether to use silent mode (only output response)
            workspace_path: Working directory for Copilot to create files in
            
        Returns:
            Tuple of (stdout, stderr, return_code)
        """
        args = [self._copilot_path, "-p", prompt]
        
        # Add model if specified
        if model:
            args.extend(["--model", model])
        elif self._default_model:
            args.extend(["--model", self._default_model])
            
        # Silent mode for cleaner output
        if silent:
            args.append("-s")
            
        # Allow all tools for non-interactive mode
        args.append("--allow-all-tools")
        
        # Disable color for cleaner parsing
        args.append("--no-color")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._get_env(),
                cwd=workspace_path  # Set working directory
            )
            
            stdout, stderr = await process.communicate()
            
            return (
                stdout.decode("utf-8", errors="replace"),
                stderr.decode("utf-8", errors="replace"),
                process.returncode or 0
            )
            
        except FileNotFoundError:
            raise Exception(
                "GitHub Copilot CLI not found. Please install it:\n"
                "- Windows: winget install GitHub.Copilot\n"
                "- macOS/Linux: brew install copilot-cli\n"
                "- npm: npm install -g @github/copilot\n"
                "Then set GH_TOKEN with a PAT that has 'Copilot Requests' permission"
            )
    
    async def check_copilot_available(self) -> Dict[str, Any]:
        """Check if GitHub Copilot CLI is available and authenticated."""
        try:
            # Check copilot CLI is installed
            process = await asyncio.create_subprocess_exec(
                self._copilot_path, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._get_env()
            )
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                return {"available": False, "error": "Copilot CLI not installed"}
            
            version = stdout.decode("utf-8", errors="replace").strip()
            
            # Check if token is set
            has_token = bool(self._gh_token)
            
            if not has_token:
                return {
                    "available": False,
                    "error": "GH_TOKEN or GITHUB_TOKEN not set. Create a PAT with 'Copilot Requests' permission.",
                    "version": version,
                    "has_token": False
                }
            
            return {
                "available": True,
                "version": version,
                "has_token": True,
                "default_model": self._default_model
            }
            
        except FileNotFoundError:
            return {
                "available": False,
                "error": "Copilot CLI not found. Install with: winget install GitHub.Copilot"
            }
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        keep_workspace: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send a chat request to GitHub Copilot CLI with temp workspace.
        
        Creates a temporary workspace, runs Copilot (which can create files),
        and returns the response along with any files created.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            model: Model to use (claude-sonnet-4, gpt-5, etc.)
            keep_workspace: If True, don't cleanup workspace (for debugging)
            
        Returns:
            Response with message content and any files created (as base64)
        """
        # Create temporary workspace for this request
        workspace_path = self._create_temp_workspace()
        
        try:
            # Build the prompt from messages
            prompt = self._build_prompt(messages)
            
            # Run copilot with the prompt in the workspace
            stdout, stderr, code = await self._run_copilot_command(
                prompt=prompt,
                model=model or self._default_model,
                workspace_path=workspace_path
            )
            
            if code != 0:
                response_text = stderr.strip() if stderr else "Copilot CLI error"
            else:
                response_text = self._parse_copilot_output(stdout)
            
            # Scan workspace for any files created
            files_created = self._scan_workspace_files(workspace_path)
            
            return self._format_response_with_files(
                prompt=prompt,
                response=response_text,
                model=model or self._default_model,
                files=files_created,
                workspace_id=os.path.basename(workspace_path)
            )
            
        finally:
            # Cleanup workspace unless told to keep it
            if not keep_workspace:
                self._cleanup_workspace(workspace_path)
    
    def _build_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Build a single prompt from message history."""
        parts = []
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                parts.append(f"System instructions: {content}")
            elif role == "user":
                parts.append(f"User: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
        
        return "\n\n".join(parts)
    
    def _parse_copilot_output(self, output: str) -> str:
        """Parse and clean Copilot CLI output."""
        if not output:
            return "No response from Copilot"
        
        # Remove ANSI escape codes
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        output = ansi_escape.sub('', output)
        
        # Clean up common CLI output patterns
        lines = output.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Skip spinner/loading lines
            if any(c in line for c in ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']):
                continue
            # Skip empty lines at start
            if not cleaned_lines and not line.strip():
                continue
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()
    
    def _format_response_with_files(
        self, 
        prompt: str, 
        response: str, 
        model: str,
        files: List[Dict[str, Any]],
        workspace_id: str
    ) -> Dict[str, Any]:
        """Format response with files in extended OpenAI-compatible format."""
        return {
            "id": f"copilot-{workspace_id}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": f"github-copilot-{model}",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(response.split()),
                "total_tokens": len(prompt.split()) + len(response.split())
            },
            "files": files,
            "files_count": len(files),
            "workspace_id": workspace_id,
            "copilot_metadata": {
                "cli_version": "copilot-cli",
                "model": model,
                "workspace_used": True
            }
        }
    
    def _format_response(self, prompt: str, response: str, model: str) -> Dict[str, Any]:
        """Format response in OpenAI-compatible format (without files)."""
        return {
            "id": f"copilot-{hash(prompt) % 10000}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": f"github-copilot-{model}",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(response.split()),
                "total_tokens": len(prompt.split()) + len(response.split())
            },
            "copilot_metadata": {
                "cli_version": "copilot-cli",
                "model": model
            }
        }
    
    async def stream_chat(
        self,
        messages: List[Dict[str, str]],
        model: str = None,
        **kwargs
    ) -> tuple[str, List[Dict[str, Any]]]:
        """
        Stream chat - simulated since CLI doesn't support native streaming.
        Returns both the stream data and the files created.
        """
        response = await self.chat(messages, model=model, **kwargs)
        
        content = response["choices"][0]["message"]["content"]
        files = response.get("files", [])
        
        # Simulate streaming by chunking the response
        chunks = []
        words = content.split(' ')
        
        for i, word in enumerate(words):
            chunk_data = {
                "id": response["id"],
                "object": "chat.completion.chunk",
                "choices": [{
                    "index": 0,
                    "delta": {"content": word + (' ' if i < len(words) - 1 else '')},
                    "finish_reason": None if i < len(words) - 1 else "stop"
                }]
            }
            chunks.append(f"data: {json.dumps(chunk_data)}\n\n")
        
        # Add files at the end of stream
        if files:
            files_chunk = {
                "id": response["id"],
                "object": "chat.completion.files",
                "files": files,
                "files_count": len(files)
            }
            chunks.append(f"data: {json.dumps(files_chunk)}\n\n")
        
        chunks.append("data: [DONE]\n\n")
        return "".join(chunks), files
    
    def get_available_models(self) -> List[Dict[str, Any]]:
        """Get list of available models from Copilot CLI."""
        return [
            {
                "id": "claude-sonnet-4.5",
                "name": "Claude Sonnet 4.5",
                "description": "Latest Claude Sonnet model",
                "provider": "anthropic"
            },
            {
                "id": "claude-sonnet-4",
                "name": "Claude Sonnet 4",
                "description": "Claude Sonnet 4 model",
                "provider": "anthropic"
            },
            {
                "id": "claude-opus-4.5",
                "name": "Claude Opus 4.5",
                "description": "Most capable Claude model",
                "provider": "anthropic"
            },
            {
                "id": "claude-haiku-4.5",
                "name": "Claude Haiku 4.5",
                "description": "Fast Claude model",
                "provider": "anthropic"
            },
            {
                "id": "gpt-5",
                "name": "GPT-5",
                "description": "OpenAI GPT-5",
                "provider": "openai"
            },
            {
                "id": "gpt-5.1",
                "name": "GPT-5.1",
                "description": "OpenAI GPT-5.1",
                "provider": "openai"
            },
            {
                "id": "gpt-5.2",
                "name": "GPT-5.2",
                "description": "OpenAI GPT-5.2",
                "provider": "openai"
            },
            {
                "id": "gpt-5-mini",
                "name": "GPT-5 Mini",
                "description": "Smaller GPT-5 model",
                "provider": "openai"
            },
            {
                "id": "gemini-3-pro-preview",
                "name": "Gemini 3 Pro Preview",
                "description": "Google Gemini 3 Pro",
                "provider": "google"
            }
        ]
