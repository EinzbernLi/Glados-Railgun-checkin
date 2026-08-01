"""Compatibility shim for older imports."""

from src.logging_config import configure_logging


def init_logger():
    return configure_logging()
