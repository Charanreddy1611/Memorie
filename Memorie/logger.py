"""
Memoire — Logging Setup
========================
Provides a pre-configured logger for every module.  All function calls are
logged at INFO level with their parameters, and all GenAI API calls are
logged with model name, prompt (truncated), config, and output summary.
Inline binary data is stripped from logs automatically.

Usage:
    from logger import get_logger
    log = get_logger(__name__)
    log.info("doing something", extra_key="value")
"""

import logging
import sys
from config import LOG_LEVEL, LOG_FILE


def get_logger(name: str) -> logging.Logger:
    """Return a named logger with console + file handlers attached once."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
        fmt = logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s — %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        logger.addHandler(console)

        try:
            fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except OSError:
            pass

    return logger


def _truncate(text, max_len: int = 200) -> str:
    """Shorten a string for log readability."""
    if text is None:
        return "None"
    s = str(text)
    return s if len(s) <= max_len else s[:max_len] + "…"


def log_genai_call(
    logger: logging.Logger,
    *,
    model: str,
    prompt: str,
    config: dict | None = None,
    output: str | None = None,
):
    """Structured log entry for any GenAI API call (Gemini, Veo, Lyria, Nano Banana)."""
    logger.info(
        "GenAI call  model=%s  prompt=%s  config=%s  output=%s",
        model,
        _truncate(prompt),
        _truncate(str(config)),
        _truncate(output),
    )
