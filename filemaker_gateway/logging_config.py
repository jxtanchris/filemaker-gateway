"""Logging configuration using Loguru."""

import sys

from loguru import logger


def setup_logging(level: str = "INFO", log_file: str | None = None) -> None:
    """Configure structured logging.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR).
        log_file: Optional file path for log output.
    """
    # Remove default handler
    logger.remove()

    # Console output with color
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # File output (JSON format for machine parsing)
    if log_file:
        logger.add(
            log_file,
            level=level,
            format="{time} | {level} | {name}:{line} | {message}",
            rotation="10 MB",
            retention="7 days",
            compression="gz",
        )
