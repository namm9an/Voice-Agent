"""
Logging configuration with rotating file handlers.
"""

import logging
from logging.handlers import RotatingFileHandler
import os


def setup_logging(log_dir: str = "logs", level: int = logging.INFO) -> None:
    os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(
        fmt='%(asctime)s %(levelname)s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    app_handler = RotatingFileHandler(os.path.join(log_dir, 'app.log'), maxBytes=10_000_000, backupCount=5)
    app_handler.setFormatter(formatter)
    app_handler.setLevel(level)

    error_handler = RotatingFileHandler(os.path.join(log_dir, 'error.log'), maxBytes=10_000_000, backupCount=5)
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        root_logger.setLevel(level)
        root_logger.addHandler(app_handler)
        root_logger.addHandler(error_handler)
        root_logger.addHandler(console_handler)