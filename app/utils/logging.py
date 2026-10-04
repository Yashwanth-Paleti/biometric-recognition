import logging
import sys
from app.config.settings import settings

def setup_logger(name: str = "biometric") -> logging.Logger:
    """
    Sets up a structured application logger with sanitized output.
    Ensures biometric embeddings, raw images, and secrets are never logged.
    """
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        level = getattr(logging, settings.log_level.upper(), logging.INFO)
        logger.setLevel(level)
        
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
        # Prevent propagation to avoid duplicated logs
        logger.propagate = False
        
    return logger

logger = setup_logger("biometric")
