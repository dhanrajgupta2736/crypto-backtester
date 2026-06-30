"""Standardized multi-level logging.

Provides segmented logging handlers per candidate and per experiment.
"""

from pathlib import Path
import logging
import sys


class CustomLogger:
    """Standardized logger supporting custom SUCCESS levels and file segregation."""

    def __init__(self, log_dir: Path) -> None:
        """Initialize directory where files will route."""
        self.log_dir: Path = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.SUCCESS_LEVEL: int = 25
        logging.addLevelName(self.SUCCESS_LEVEL, "SUCCESS")

    def get_experiment_logger(self, candidate_id: str, experiment_id: str) -> logging.Logger:
        """Create or retrieve a file-segregated logger for a specific experiment.
        
        Args:
            candidate_id (str): The strategy candidate identifier.
            experiment_id (str): Unique experiment run ID.
            
        Returns:
            logging.Logger: Logger instance directed to write in the candidate's output log path.
        """
        logger_name = f"{candidate_id}_{experiment_id}"
        logger = logging.getLogger(logger_name)
        
        # Avoid duplicate handlers if logger was already created
        if logger.handlers:
            return logger
            
        logger.setLevel(logging.DEBUG)

        # File Handler
        candidate_log_dir = self.log_dir / candidate_id / "logs"
        candidate_log_dir.mkdir(parents=True, exist_ok=True)
        log_file = candidate_log_dir / f"{experiment_id}.log"
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter(
            fmt='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        return logger

    def success(self, logger: logging.Logger, message: str, *args, **kwargs) -> None:
        """Log a message with 'SUCCESS' level."""
        if logger.isEnabledFor(self.SUCCESS_LEVEL):
            logger.log(self.SUCCESS_LEVEL, message, *args, **kwargs)
