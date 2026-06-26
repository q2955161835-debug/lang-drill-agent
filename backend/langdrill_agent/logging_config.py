from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Any

from .config import load_settings


def configure_logging(*, force: bool = False) -> dict[str, Any]:
    settings = load_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    log_file = settings.log_dir / "langdrill-agent.log"
    root = logging.getLogger()
    if root.handlers and not force:
        return {"log_dir": settings.log_dir, "log_file": log_file}

    level_name = os.getenv("LANGDRILL_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root.handlers.clear()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)
    logging.getLogger("langdrill_agent").setLevel(level)
    logging.getLogger(__name__).info("logging configured", extra={"log_file": str(log_file)})
    return {"log_dir": settings.log_dir, "log_file": log_file}
