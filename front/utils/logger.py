import logging
import sys
from pathlib import Path

_LOG_DIR = Path("logs")
_LOG_FILE = _LOG_DIR / "app.log"


def setup_logger(name: str = __name__) -> logging.Logger:
    """Configure and return the application logger."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # File handler
    fh = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    ffmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    fh.setFormatter(ffmt)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    cfmt = logging.Formatter("[%(levelname)s] %(message)s")
    ch.setFormatter(cfmt)
    logger.addHandler(ch)

    return logger


logger = setup_logger("training_viewer")
