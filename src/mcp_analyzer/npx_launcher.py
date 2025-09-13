"""NPX MCP server launcher and process management."""

import asyncio
import logging
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

if sys.platform != "win32":
    import fcntl
    import select

logger = logging.getLogger(__name__)


def _get_safe_env_summary(env: dict) -> str:
    """Get a safe summary of environment variables for logging."""

    sensitive_patterns = [
        "api_key",
        "apikey",
        "key",
        "secret",
        "password",
        "passwd",
        "pwd",
        "token",
        "auth",
        "credential",
        "cred",
        "private",
        "access",
        "session",
        "cookie",
        "oauth",
        "jwt",
        "bearer",
        "signature",
        "database_url",
        "db_url",
        "connection_string",
        "dsn",
    ]

    safe_vars = []
    sensitive_count = 0

    for key in env.keys():
        key_lower = key.lower()
        is_sensitive = any(pattern in key_lower for pattern in sensitive_patterns)

        if is_sensitive:
            sensitive_count += 1
        else:
            safe_vars.append(key)

    # Create summary
    summary_parts = []
    if safe_vars:
        # Show only first few safe variables to avoid log spam
        if len(safe_vars) <= 5:
            summary_parts.append(f"safe: {safe_vars}")
        else:
            summary_parts.append(f"safe: {safe_vars[:3]} + {len(safe_vars) - 3} more")

    if sensitive_count > 0:
        summary_parts.append(f"sensitive: {sensitive_count} hidden")

    return f"{{{', '.join(summary_parts)}}}"


@dataclass
class NPXServerConfig:
    """Configuration for NPX-launched MCP server."""

    command: str
    env_vars: Dict[str, str]
    working_dir: Optional[str] = None
    timeout: int = 30
    port: Optional[int] = None
    log_env_vars: bool = True


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
            logger.info(f"Working directory: {self.config.working_dir}")

            if self.config.log_env_vars:
                logger.info(f"Environment variables: {_get_safe_env_summary(env)}")
            else:
                logger.debug("Environment variable logging disabled for security")

            # Start the process
            self.process = subprocess.Popen(
                cmd_parts,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.config.working_dir,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            logger.info(f"Process started with PID: {self.process.pid}")

            # Wait for server to be ready and extract URL
            self.server_url = await self._wait_for_server_ready()

            logger.info(f"NPX server started successfully at {self.server_url}")
            return self.server_url

        except NPXLauncherError:
            await self.stop()
            raise  # Re-raise NPXLauncherError as-is
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
                        asyncio.create_task(self._wait_for_process_end()), timeout=5.0
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
        if "&&" in command:
            parts = command.split("&&")
            # The NPX command should be the last part
            npx_command = parts[-1].strip()
        else:
            npx_command = command

        # Parse the NPX command
        cmd_parts = shlex.split(npx_command)

        # Ensure we're using npx
        if not cmd_parts or cmd_parts[0] != "npx":
            raise NPXLauncherError(
                f"Command must start with 'npx', got: {cmd_parts[0] if cmd_parts else 'empty'}"
            )

        return cmd_parts

    def _prepare_environment(self) -> Dict[str, str]:
        """Prepare environment variables for the process."""
        env = os.environ.copy()

        # Add configured environment variables
        env.update(self.config.env_vars)

        # Extract env vars from command if present
        command = self.config.command.strip()
        if "&&" in command:
            env_part = command.split("&&")[0].strip()
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
            r"export\s+([A-Z_][A-Z0-9_]*)=([^\s&]+)",  # export VAR=value
            r"([A-Z_][A-Z0-9_]*)=([^\s&]+)",  # VAR=value
        ]

        for pattern in patterns:
            matches = re.findall(pattern, env_string)
            for var_name, var_value in matches:
                # Remove quotes if present
                var_value = var_value.strip("\"'")
                env_vars[var_name] = var_value

        return env_vars

    async def _wait_for_server_ready(self) -> str:
        """Wait for server to start and extract its URL."""
        start_time = time.time()
        output_lines = []
        stdout_buffer = ""
        stderr_buffer = ""
        last_activity = start_time

        logger.info(
            f"Waiting for NPX server to start (timeout: {self._startup_timeout}s)"
        )

        # Make stdout and stderr non-blocking
        self._make_non_blocking(self.process.stdout)
        self._make_non_blocking(self.process.stderr)

        loop_count = 0
        while time.time() - start_time < self._startup_timeout:
            loop_count += 1
            current_time = time.time()

            # Log progress every 5 seconds
            if loop_count % 50 == 0:  # Every 5 seconds (50 * 0.1s sleep)
                elapsed = current_time - start_time
                process_alive = self.process.poll() is None
                logger.info(
                    f"Still waiting for server... ({elapsed:.1f}s elapsed, process alive: {process_alive})"
                )
                if current_time - last_activity > 10:
                    logger.warning(
                        f"No output received for {current_time - last_activity:.1f}s"
                    )

                # If no output for too long, try to check if process is doing something
                if current_time - last_activity > 20 and process_alive:
                    logger.warning(
                        "Process is running but producing no output. This might indicate:"
                    )
                    logger.warning("1. The NPX package is being downloaded/installed")
                    logger.warning(
                        "2. The server is starting but not logging to stdout/stderr"
                    )
                    logger.warning("3. The server is waiting for input or has an error")
            if self.process.poll() is not None:
                # Process has terminated - read any remaining output
                remaining_stdout, remaining_stderr = self.process.communicate()
                if remaining_stdout:
                    stdout_buffer += remaining_stdout
                if remaining_stderr:
                    stderr_buffer += remaining_stderr

                all_output = f"STDOUT:\n{stdout_buffer}\nSTDERR:\n{stderr_buffer}"
                raise NPXLauncherError(
                    f"NPX process terminated unexpectedly. "
                    f"Exit code: {self.process.returncode}\n{all_output}"
                )

            # Read available output without blocking
            try:
                # Read from stdout
                stdout_data = self._read_non_blocking(self.process.stdout)
                if stdout_data:
                    last_activity = current_time
                    stdout_buffer += stdout_data
                    # Process complete lines
                    lines = stdout_buffer.split("\n")
                    stdout_buffer = lines[-1]  # Keep incomplete line

                    for line in lines[:-1]:
                        if line.strip():
                            output_lines.append(f"STDOUT: {line.strip()}")
                            logger.info(f"NPX stdout: {line.strip()}")

                            # Try to extract server URL from output
                            url = self._extract_server_url(line)
                            if url:
                                logger.info(f"Found server URL: {url}")
                                return url

                # Read from stderr
                stderr_data = self._read_non_blocking(self.process.stderr)
                if stderr_data:
                    last_activity = current_time
                    stderr_buffer += stderr_data
                    # Process complete lines
                    lines = stderr_buffer.split("\n")
                    stderr_buffer = lines[-1]  # Keep incomplete line

                    for line in lines[:-1]:
                        if line.strip():
                            output_lines.append(f"STDERR: {line.strip()}")
                            logger.info(f"NPX stderr: {line.strip()}")

                            # Try to extract server URL from stderr too
                            url = self._extract_server_url(line)
                            if url:
                                logger.info(f"Found server URL in stderr: {url}")
                                return url

            except Exception as e:
                logger.debug(f"Error reading process output: {e}")

            await asyncio.sleep(0.1)

        # Timeout reached - try fallback detection
        logger.warning(
            f"Timeout reached after {self._startup_timeout}s, trying fallback server detection..."
        )

        # Try common ports for MCP servers
        fallback_url = await self._try_fallback_detection()
        if fallback_url:
            logger.info(f"Fallback detection found server at: {fallback_url}")
            return fallback_url

        # No fallback worked, raise timeout error
        all_output = "\n".join(output_lines)

        # Add process status to error message
        process_status = (
            "running"
            if self.process.poll() is None
            else f"terminated (exit code: {self.process.returncode})"
        )

        # Generate troubleshooting suggestions
        troubleshooting = self._generate_troubleshooting_suggestions(
            all_output, process_status
        )

        raise NPXLauncherError(
            f"Timeout waiting for NPX server to start after {self._startup_timeout}s. "
            f"Process status: {process_status}. "
            f"Output: {all_output if all_output else 'No output captured'}. "
            f"Troubleshooting: {troubleshooting}"
        )

    def _extract_server_url(self, line: str) -> Optional[str]:
        """Extract server URL from output line."""
        # Common patterns for MCP server URLs - more comprehensive
        url_patterns = [
            # Explicit server messages
            r"(?:Server|MCP|server)\s+(?:running|started|listening)\s+(?:on|at)?\s*(https?://[^\s]+)",
            r"(?:Available|Serving)\s+(?:on|at)?\s*(https?://[^\s]+)",
            r"(?:URL|url):\s*(https?://[^\s]+)",
            r"(?:Listening|listening)\s+(?:on|at)?\s*(https?://[^\s]+)",
            # Generic URL patterns
            r"(https?://(?:localhost|127\.0\.0\.1):\d+(?:/[^\s]*)?)",
            r"(http://[^\s:]+:\d+(?:/[^\s]*)?)",
            # Port-based patterns (common for development servers)
            r"(?:port|Port)\s+(\d+)",  # Extract port and construct URL
            r"(?:localhost|127\.0\.0\.1):(\d+)",  # Extract localhost:port
        ]

        for pattern in url_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                url_or_port = match.group(1).rstrip(".,;")

                # If we found just a port number, construct the URL
                if url_or_port.isdigit():
                    url = f"http://localhost:{url_or_port}"
                else:
                    url = url_or_port

                # Validate URL format
                if self._is_valid_url(url):
                    return url

        return None

    def _is_valid_url(self, url: str) -> bool:
        """Validate if extracted URL looks reasonable."""
        return (
            url.startswith(("http://", "https://"))
            and ("localhost" in url or "127.0.0.1" in url)
            and ":" in url
        )

    async def _try_fallback_detection(self) -> Optional[str]:
        """Try to detect server on common ports as a fallback."""
        import socket

        # Common ports used by MCP servers and development tools
        common_ports = [3000, 3001, 8000, 8080, 4000, 5000, 9000]

        # If a specific port was configured, try it first
        if self.config.port:
            common_ports.insert(0, self.config.port)

        for port in common_ports:
            try:
                # Try to connect to the port
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1.0)  # Quick timeout
                    result = sock.connect_ex(("localhost", port))
                    if result == 0:
                        # Port is open, try to validate it's an HTTP server
                        test_url = f"http://localhost:{port}"
                        if await self._test_http_endpoint(test_url):
                            return test_url
            except Exception as e:
                logger.debug(f"Failed to test port {port}: {e}")
                continue

        return None

    async def _test_http_endpoint(self, url: str) -> bool:
        """Test if a URL responds to HTTP requests."""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.get(url)
                # Any HTTP response (even 404) indicates a web server
                return True
        except Exception:
            return False

    def _generate_troubleshooting_suggestions(
        self, output: str, process_status: str
    ) -> str:
        """Generate helpful troubleshooting suggestions based on the failure."""
        suggestions = []

        if "No output captured" in output or not output.strip():
            suggestions.append("The NPX process produced no output. This could mean:")
            suggestions.append(
                "- The package is being downloaded/installed (try increasing timeout)"
            )
            suggestions.append("- The package name is incorrect or doesn't exist")
            suggestions.append("- Network issues preventing package download")
            suggestions.append("- The package doesn't start an HTTP server")

        if "running" in process_status:
            suggestions.append("Process is still running but not responding. Try:")
            suggestions.append(
                "- Check if the package requires additional configuration"
            )
            suggestions.append("- Verify the package starts an HTTP server by default")
            suggestions.append("- Check if the package is waiting for input")

        if "terminated" in process_status:
            suggestions.append("Process terminated unexpectedly. Check:")
            suggestions.append("- If the package exists and is an MCP server")
            suggestions.append("- Required environment variables are set")
            suggestions.append("- Dependencies are installed")

        # Add command-specific suggestions
        cmd_parts = self._parse_command()
        if len(cmd_parts) > 1:
            package_name = cmd_parts[1]
            suggestions.append(f"To debug manually, try running: {' '.join(cmd_parts)}")
            suggestions.append(f"Or test if package exists: npx {package_name} --help")

        return " ".join(suggestions)

    def _make_non_blocking(self, file_obj) -> None:
        """Make a file object non-blocking (cross-platform)."""
        if not file_obj:
            return

        if sys.platform == "win32":
            # On Windows, we'll use polling instead of making truly non-blocking
            pass
        else:
            # Unix-like systems
            fd = file_obj.fileno()
            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    def _read_non_blocking(self, file_obj) -> str:
        """Read from a file object without blocking (cross-platform)."""
        if not file_obj:
            return ""

        if sys.platform == "win32":
            # Windows: use select to check if data is available
            try:
                ready, _, _ = select.select([file_obj], [], [], 0)
                if ready:
                    data = file_obj.read()
                    return data if data else ""
                return ""
            except (OSError, ValueError):
                return ""
        else:
            # Unix-like systems: use non-blocking read
            try:
                data = file_obj.read()
                return data if data else ""
            except (BlockingIOError, OSError):
                return ""

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
        env_vars = kwargs.get("env_vars", {})

        config = NPXServerConfig(
            command=command,
            env_vars=env_vars,
            working_dir=kwargs.get("working_dir"),
            timeout=kwargs.get("timeout", 30),
            port=kwargs.get("port"),
            log_env_vars=kwargs.get("log_env_vars", True),
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

    if "&&" in command:
        parts = command.split("&&")
        env_part = parts[0].strip()
        npx_part = "&&".join(parts[1:]).strip()

        # Parse environment variables
        env_patterns = [
            r"export\s+([A-Z_][A-Z0-9_]*)=([^\s&]+)",
            r"([A-Z_][A-Z0-9_]*)=([^\s&]+)",
        ]

        for pattern in env_patterns:
            matches = re.findall(pattern, env_part)
            for var_name, var_value in matches:
                var_value = var_value.strip("\"'")
                env_vars[var_name] = var_value
    else:
        npx_part = command.strip()

    return npx_part, env_vars


def is_npx_command(command: str) -> bool:
    """Check if a command is an NPX command."""
    # Clean up the command to get the main part
    if "&&" in command:
        command = command.split("&&")[-1].strip()

    return command.strip().startswith("npx ")
