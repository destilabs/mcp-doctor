"""Cache manager for successful tool calls during token efficiency testing."""

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ToolCallCache:
    """
    Manages caching of successful tool calls with inputs and outputs.

    Stores results in ~/.mcp-analyzer/tool-call-cache/{server_hash}/{tool_name}/
    """

    def __init__(self, server_url: str, cache_dir: Optional[Path] = None):
        """
        Initialize tool call cache.

        Args:
            server_url: URL of the MCP server (used for cache namespacing)
            cache_dir: Optional custom cache directory (defaults to ~/.mcp-analyzer/tool-call-cache)
        """
        self.server_url = server_url

        if cache_dir is None:
            cache_dir = Path.home() / ".mcp-analyzer" / "tool-call-cache"

        server_hash = self._hash_server_url(server_url)
        self.cache_root = cache_dir / server_hash
        self.cache_root.mkdir(parents=True, exist_ok=True)

        metadata_file = self.cache_root / "_metadata.json"
        if not metadata_file.exists():
            self._write_metadata(metadata_file)

        logger.debug(f"Tool call cache initialized at {self.cache_root}")

    def _hash_server_url(self, url: str) -> str:
        """Create a short hash of the server URL for directory naming."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _write_metadata(self, metadata_file: Path) -> None:
        """Write metadata about this cache directory."""
        metadata = {
            "server_url": self.server_url,
            "created_at": datetime.utcnow().isoformat(),
            "description": "Cache of successful MCP tool calls for token efficiency testing",
        }
        metadata_file.write_text(json.dumps(metadata, indent=2))

    def cache_successful_call(
        self,
        tool_name: str,
        input_params: Dict[str, Any],
        output_response: Any,
        token_count: int,
        response_time: float,
        scenario: str = "unknown",
    ) -> None:
        """
        Cache a successful tool call.

        Args:
            tool_name: Name of the tool that was called
            input_params: Parameters used to call the tool
            output_response: Response from the tool
            token_count: Estimated token count of the response
            response_time: Time taken to execute the call
            scenario: Scenario name (e.g., "minimal", "typical", "llm_corrected")
        """
        try:
            tool_dir = self.cache_root / self._sanitize_tool_name(tool_name)
            tool_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
            call_file = tool_dir / f"{scenario}_{timestamp}.json"

            call_data = {
                "tool_name": tool_name,
                "server_url": self.server_url,
                "timestamp": datetime.utcnow().isoformat(),
                "scenario": scenario,
                "input_params": input_params,
                "output_response": output_response,
                "metrics": {
                    "token_count": token_count,
                    "response_time_seconds": response_time,
                    "response_size_bytes": len(
                        json.dumps(output_response, ensure_ascii=False)
                    ),
                },
            }

            call_file.write_text(
                json.dumps(call_data, indent=2, ensure_ascii=False, default=str)
            )
            logger.debug(
                f"Cached successful call: {tool_name} ({scenario}) -> {call_file}"
            )

            self._update_tool_index(tool_dir, tool_name)

        except Exception as e:
            logger.warning(f"Failed to cache tool call for {tool_name}: {e}")

    def _update_tool_index(self, tool_dir: Path, tool_name: str) -> None:
        """Update the index file for a tool with call statistics."""
        try:
            index_file = tool_dir / "_index.json"

            if index_file.exists():
                index_data = json.loads(index_file.read_text())
            else:
                index_data = {
                    "tool_name": tool_name,
                    "total_cached_calls": 0,
                    "first_cached": datetime.utcnow().isoformat(),
                    "scenarios": {},
                }

            index_data["total_cached_calls"] += 1
            index_data["last_cached"] = datetime.utcnow().isoformat()

            call_files = list(tool_dir.glob("*.json"))
            call_files = [f for f in call_files if not f.name.startswith("_")]

            scenario_counts: Dict[str, int] = {}
            for call_file in call_files:
                try:
                    call_data = json.loads(call_file.read_text())
                    scenario = call_data.get("scenario", "unknown")
                    scenario_counts[scenario] = scenario_counts.get(scenario, 0) + 1
                except Exception:
                    pass

            index_data["scenarios"] = scenario_counts

            index_file.write_text(json.dumps(index_data, indent=2, ensure_ascii=False))

        except Exception as e:
            logger.debug(f"Failed to update tool index for {tool_name}: {e}")

    def _sanitize_tool_name(self, tool_name: str) -> str:
        """Sanitize tool name for use as directory name."""
        sanitized = tool_name.replace("/", "_").replace("\\", "_").replace(" ", "_")
        sanitized = "".join(c for c in sanitized if c.isalnum() or c in "-_")
        return sanitized or "unknown_tool"

    def get_cached_calls(self, tool_name: str, scenario: Optional[str] = None) -> list:
        """
        Retrieve cached calls for a tool.

        Args:
            tool_name: Name of the tool
            scenario: Optional scenario filter

        Returns:
            List of cached call data
        """
        try:
            tool_dir = self.cache_root / self._sanitize_tool_name(tool_name)
            if not tool_dir.exists():
                return []

            cached_calls = []
            for call_file in tool_dir.glob("*.json"):
                if call_file.name.startswith("_"):
                    continue

                try:
                    call_data = json.loads(call_file.read_text())
                    if scenario is None or call_data.get("scenario") == scenario:
                        cached_calls.append(call_data)
                except Exception as e:
                    logger.debug(f"Failed to read cached call {call_file}: {e}")

            return sorted(
                cached_calls, key=lambda x: x.get("timestamp", ""), reverse=True
            )

        except Exception as e:
            logger.warning(f"Failed to retrieve cached calls for {tool_name}: {e}")
            return []

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the cache."""
        try:
            tools: Dict[str, Any] = {}
            total_tools = 0
            total_calls = 0

            for tool_dir in self.cache_root.iterdir():
                if not tool_dir.is_dir() or tool_dir.name.startswith("_"):
                    continue

                index_file = tool_dir / "_index.json"
                if index_file.exists():
                    try:
                        index_data = json.loads(index_file.read_text())
                        tool_name = index_data.get("tool_name", tool_dir.name)
                        tools[str(tool_name)] = index_data
                        total_tools += 1
                        total_calls += int(index_data.get("total_cached_calls", 0))
                    except Exception:
                        pass

            return {
                "server_url": self.server_url,
                "cache_path": str(self.cache_root),
                "total_tools": total_tools,
                "total_calls": total_calls,
                "tools": tools,
            }

        except Exception as e:
            logger.warning(f"Failed to get cache stats: {e}")
            return {"error": str(e)}

    def clear_cache(self, tool_name: Optional[str] = None) -> None:
        """
        Clear cached calls.

        Args:
            tool_name: If provided, clear only this tool's cache. Otherwise clear all.
        """
        try:
            if tool_name:
                tool_dir = self.cache_root / self._sanitize_tool_name(tool_name)
                if tool_dir.exists():
                    import shutil

                    shutil.rmtree(tool_dir)
                    logger.info(f"Cleared cache for tool: {tool_name}")
            else:
                import shutil

                if self.cache_root.exists():
                    shutil.rmtree(self.cache_root)
                    self.cache_root.mkdir(parents=True, exist_ok=True)
                    metadata_file = self.cache_root / "_metadata.json"
                    self._write_metadata(metadata_file)
                    logger.info(f"Cleared all cache for server: {self.server_url}")

        except Exception as e:
            logger.warning(f"Failed to clear cache: {e}")
