import asyncio
import logging
from functools import wraps
from typing import Callable, Any

logger = logging.getLogger(__name__)

def retry_async(retries: int = 3, delay: float = 1.0, backoff: float = 2.0, exceptions: tuple = (Exception,)):
    """
    Retry an async function multiple times.
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            curr_delay = delay
            last_exception = None
            for i in range(retries):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if i < retries - 1:
                        logger.warning(
                            f"Retry {i+1}/{retries} for {func.__name__} due to {type(e).__name__}: {e}. "
                            f"Sleeping {curr_delay}s..."
                        )
                        await asyncio.sleep(curr_delay)
                        curr_delay *= backoff
                    else:
                        logger.error(f"All {retries} retries failed for {func.__name__}")
            
            if last_exception:
                raise last_exception
        return wrapper
    return decorator
