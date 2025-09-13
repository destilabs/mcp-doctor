"""NPX MCP server launcher and process management."""

import asyncio
import logging
import os
import re
import shlex
import subprocess
import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class NPXServerConfig:
    """Configuration for NPX-launched MCP server."""
    command: str
    env_vars: Dict[str, str]
    working_dir: Optional[str] = None
    timeout: int = 30
    port: Optional[int] = None
    
    
class NPXServerProcess:
    """Manages NPX MCP server process lifecycle."""
    
    def __init__(self, config: NPXServerConfig):
        self.config = config
        self.process: Optional[subprocess.Popen] = None
        self.server_url: Optional[str] = None
        self._startup_timeout = config.timeout
        
    async def start(self) -> str:
        """
        Start the NPX server and return its URL.
        
        Returns:
            Server URL once it's ready to accept connections
            
        Raises:
            NPXLauncherError: If server fails to start or times out
        """
        try:
            # Parse and prepare the command
            cmd_parts = self._parse_command()
            env = self._prepare_environment()
            
            logger.info(f"Starting NPX server: {' '.join(cmd_parts)}")
            
            # Start the process
            self.process = subprocess.Popen(
                cmd_parts,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.config.working_dir,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Wait for server to be ready and extract URL
            self.server_url = await self._wait_for_server_ready()
            
            logger.info(f"NPX server started successfully at {self.server_url}")
            return self.server_url
            
        except Exception as e:
            await self.stop()
            raise NPXLauncherError(f"Failed to start NPX server: {e}")
    
    async def stop(self) -> None:
        """Stop the NPX server process."""
        if self.process:
            try:
                # Try graceful shutdown first
                self.process.terminate()
                
                # Wait a bit for graceful shutdown
                try:
                    await asyncio.wait_for(
                        asyncio.create_task(self._wait_for_process_end()),
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    # Force kill if graceful shutdown failed
                    logger.warning("Graceful shutdown timed out, forcing kill")
                    self.process.kill()
                    
                # Clean up
                self.process = None
                self.server_url = None
                
                logger.info("NPX server stopped")
                
            except Exception as e:
                logger.error(f"Error stopping NPX server: {e}")
    
    def _parse_command(self) -> List[str]:
        """Parse the NPX command into components."""
        # Handle environment variables at the start of command
        command = self.config.command.strip()
        
        # Split on && to handle env vars
        if '&&' in command:
            parts = command.split('&&')
            # The NPX command should be the last part
            npx_command = parts[-1].strip()
        else:
            npx_command = command
        
        # Parse the NPX command
        cmd_parts = shlex.split(npx_command)
        
        # Ensure we're using npx
        if not cmd_parts or cmd_parts[0] != 'npx':
            raise NPXLauncherError(f"Command must start with 'npx', got: {cmd_parts[0] if cmd_parts else 'empty'}")
        
        return cmd_parts
    
    def _prepare_environment(self) -> Dict[str, str]:
        """Prepare environment variables for the process."""
        env = os.environ.copy()
        
        # Add configured environment variables
        env.update(self.config.env_vars)
        
        # Extract env vars from command if present
        command = self.config.command.strip()
        if '&&' in command:
            env_part = command.split('&&')[0].strip()
            # Parse environment variable assignments
            env_assignments = self._parse_env_assignments(env_part)
            env.update(env_assignments)
        
        return env
    
    def _parse_env_assignments(self, env_string: str) -> Dict[str, str]:
        """Parse environment variable assignments from string."""
        env_vars = {}
        
        # Look for VAR=value patterns
        # Handle both 'export VAR=value' and 'VAR=value' formats
        patterns = [
            r'export\s+([A-Z_][A-Z0-9_]*)=([^\s&&]+)',  # export VAR=value
            r'([A-Z_][A-Z0-9_]*)=([^\s&&]+)'  # VAR=value
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, env_string)
            for var_name, var_value in matches:
                # Remove quotes if present
                var_value = var_value.strip('"\'')
                env_vars[var_name] = var_value
        
        return env_vars
    
    async def _wait_for_server_ready(self) -> str:
        """Wait for server to start and extract its URL."""
        start_time = time.time()
        output_lines = []
        
        while time.time() - start_time < self._startup_timeout:
            if self.process.poll() is not None:
                # Process has terminated
                stdout, stderr = self.process.communicate()
                raise NPXLauncherError(
                    f"NPX process terminated unexpectedly. "
                    f"Exit code: {self.process.returncode}\n"
                    f"STDOUT: {stdout}\nSTDERR: {stderr}"
                )
            
            # Read available output
            try:
                # Check if there's output available
                if self.process.stdout.readable():
                    line = self.process.stdout.readline()
                    if line:
                        output_lines.append(line.strip())
                        logger.debug(f"NPX output: {line.strip()}")
                        
                        # Try to extract server URL from output
                        url = self._extract_server_url(line)
                        if url:
                            return url
                
                # Also check stderr for server info
                if self.process.stderr.readable():
                    line = self.process.stderr.readline()
                    if line:
                        output_lines.append(line.strip())
                        logger.debug(f"NPX stderr: {line.strip()}")
                        
                        # Try to extract server URL from stderr too
                        url = self._extract_server_url(line)
                        if url:
                            return url
                
            except Exception as e:
                logger.debug(f"Error reading process output: {e}")
            
            await asyncio.sleep(0.1)
        
        # Timeout reached
        all_output = '\n'.join(output_lines)
        raise NPXLauncherError(
            f"Timeout waiting for NPX server to start after {self._startup_timeout}s. "
            f"Output: {all_output}"
        )
    
    def _extract_server_url(self, line: str) -> Optional[str]:
        """Extract server URL from output line."""
        # Common patterns for MCP server URLs
        url_patterns = [
            r'(?:Server|MCP|server)\s+(?:running|started|listening)\s+(?:on|at)?\s*(https?://[^\s]+)',
            r'(?:Available|Serving)\s+(?:on|at)?\s*(https?://[^\s]+)',
            r'(https?://(?:localhost|127\.0\.0\.1):\d+(?:/[^\s]*)?)',
            r'(?:URL|url):\s*(https?://[^\s]+)',
        ]
        
        for pattern in url_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                url = match.group(1).rstrip('.,;')
                # Validate URL format
                if self._is_valid_url(url):
                    return url
        
        return None
    
    def _is_valid_url(self, url: str) -> bool:
        """Validate if extracted URL looks reasonable."""
        return (
            url.startswith(('http://', 'https://')) and
            ('localhost' in url or '127.0.0.1' in url) and
            ':' in url
        )
    
    async def _wait_for_process_end(self) -> None:
        """Wait for process to terminate."""
        while self.process and self.process.poll() is None:
            await asyncio.sleep(0.1)


class NPXLauncherError(Exception):
    """Exception raised by NPX launcher."""
    pass


class NPXServerManager:
    """High-level manager for NPX MCP servers."""
    
    def __init__(self):
        self._active_servers: Dict[str, NPXServerProcess] = {}
    
    async def launch_server(self, command: str, **kwargs) -> str:
        """
        Launch an NPX MCP server and return its URL.
        
        Args:
            command: NPX command to run (e.g., "export API_KEY=xyz && npx firecrawl-mcp")
            **kwargs: Additional configuration options
            
        Returns:
            Server URL once ready
        """
        # Parse environment variables and command
        env_vars = kwargs.get('env_vars', {})
        
        config = NPXServerConfig(
            command=command,
            env_vars=env_vars,
            working_dir=kwargs.get('working_dir'),
            timeout=kwargs.get('timeout', 30),
            port=kwargs.get('port')
        )
        
        server = NPXServerProcess(config)
        server_url = await server.start()
        
        # Store for cleanup later
        self._active_servers[server_url] = server
        
        return server_url
    
    async def stop_server(self, server_url: str) -> None:
        """Stop a specific server."""
        if server_url in self._active_servers:
            await self._active_servers[server_url].stop()
            del self._active_servers[server_url]
    
    async def stop_all_servers(self) -> None:
        """Stop all active servers."""
        for server in list(self._active_servers.values()):
            await server.stop()
        self._active_servers.clear()
    
    def get_active_servers(self) -> List[str]:
        """Get list of active server URLs."""
        return list(self._active_servers.keys())


def parse_npx_command(command: str) -> Tuple[str, Dict[str, str]]:
    """
    Parse NPX command to extract environment variables and clean command.
    
    Args:
        command: Full command string (e.g., "export API_KEY=xyz && npx firecrawl-mcp")
        
    Returns:
        Tuple of (clean_npx_command, env_vars_dict)
    """
    env_vars = {}
    
    if '&&' in command:
        parts = command.split('&&')
        env_part = parts[0].strip()
        npx_part = '&&'.join(parts[1:]).strip()
        
        # Parse environment variables
        env_patterns = [
            r'export\s+([A-Z_][A-Z0-9_]*)=([^\s&&]+)',
            r'([A-Z_][A-Z0-9_]*)=([^\s&&]+)'
        ]
        
        for pattern in env_patterns:
            matches = re.findall(pattern, env_part)
            for var_name, var_value in matches:
                var_value = var_value.strip('"\'')
                env_vars[var_name] = var_value
    else:
        npx_part = command.strip()
    
    return npx_part, env_vars


def is_npx_command(command: str) -> bool:
    """Check if a command is an NPX command."""
    # Clean up the command to get the main part
    if '&&' in command:
        command = command.split('&&')[-1].strip()
    
    return command.strip().startswith('npx ')
