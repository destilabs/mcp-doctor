"""Utility functions for MCP analyzer."""

import asyncio
from functools import wraps
from typing import Any, Callable, TypeVar, Dict
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')


def async_retry(retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Decorator to retry async functions with exponential backoff.
    
    Args:
        retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay on each retry
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            current_delay = delay
            last_exception = None
            
            for attempt in range(retries + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt == retries:
                        break
                    
                    logger.warning(
                        f"Attempt {attempt + 1} failed for {func.__name__}: {e}. "
                        f"Retrying in {current_delay}s..."
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff
            
            logger.error(f"All {retries + 1} attempts failed for {func.__name__}")
            raise last_exception
            
        return wrapper
    return decorator


def safe_get_nested(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    """
    Safely get nested dictionary values using dot notation.
    
    Args:
        data: Dictionary to search in
        path: Dot-separated path (e.g., "server.info.version")
        default: Default value if path not found
        
    Returns:
        Value at path or default
    """
    try:
        keys = path.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return default
                
        return current
        
    except (KeyError, TypeError, AttributeError):
        return default


def normalize_tool_name(name: str) -> str:
    """
    Normalize tool name for consistent comparison.
    
    Args:
        name: Original tool name
        
    Returns:
        Normalized tool name
    """
    if not name:
        return "unknown_tool"
    
    # Remove common prefixes/suffixes
    name = name.strip()
    
    # Convert to lowercase for comparison
    normalized = name.lower()
    
    # Remove common API patterns
    patterns_to_remove = ["api_", "_api", "handler_", "_handler", "endpoint_", "_endpoint"]
    for pattern in patterns_to_remove:
        if normalized.startswith(pattern) or normalized.endswith(pattern):
            normalized = normalized.replace(pattern, "")
    
    return normalized.strip("_")


def format_percentage(value: float, total: float) -> str:
    """
    Format a percentage with proper handling of edge cases.
    
    Args:
        value: Numerator value
        total: Denominator value
        
    Returns:
        Formatted percentage string
    """
    if total == 0:
        return "0%"
    
    percentage = (value / total) * 100
    
    if percentage == 0:
        return "0%"
    elif percentage < 0.1:
        return "<0.1%"
    elif percentage >= 99.95:
        return "100%"
    else:
        return f"{percentage:.1f}%"


def truncate_text(text: str, max_length: int = 50, suffix: str = "...") -> str:
    """
    Truncate text to a maximum length.
    
    Args:
        text: Text to truncate
        max_length: Maximum allowed length
        suffix: Suffix to add when truncating
        
    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text
    
    return text[:max_length - len(suffix)] + suffix


class AnalysisCache:
    """Simple in-memory cache for analysis results."""
    
    def __init__(self, ttl_seconds: int = 300):  # 5 minute TTL
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = ttl_seconds
    
    def get(self, key: str) -> Any:
        """Get cached value if not expired."""
        if key not in self._cache:
            return None
        
        entry = self._cache[key]
        import time
        
        if time.time() - entry['timestamp'] > self._ttl:
            del self._cache[key]
            return None
        
        return entry['value']
    
    def set(self, key: str, value: Any) -> None:
        """Set cached value with current timestamp."""
        import time
        self._cache[key] = {
            'value': value,
            'timestamp': time.time()
        }
    
    def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()


# Global cache instance
analysis_cache = AnalysisCache()


def validate_url(url: str) -> bool:
    """
    Validate if URL is properly formatted.
    
    Args:
        url: URL to validate
        
    Returns:
        True if URL appears valid
    """
    import re
    
    url_pattern = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    return url_pattern.match(url) is not None


def setup_logging(level: str = "INFO") -> None:
    """
    Setup logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR)
    """
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Suppress noisy third-party loggers
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
