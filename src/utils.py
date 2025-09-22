"""Utility functions for Azure AI Foundry Chatbot."""

import logging
from typing import Any, Dict


def setup_logging(level: int = logging.INFO) -> None:
    """Setup logging configuration.
    
    Args:
        level: Logging level (default: INFO)
    """
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


def get_logger(name: str) -> logging.Logger:
    """Get logger instance.
    
    Args:
        name: Logger name
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


def safe_get(dictionary: Dict[str, Any], key: str, default: Any = None) -> Any:
    """Safely get value from dictionary.
    
    Args:
        dictionary: Dictionary to get value from
        key: Key to look for
        default: Default value if key not found
        
    Returns:
        Value from dictionary or default
    """
    return dictionary.get(key, default) if dictionary else default
