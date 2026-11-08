"""Concise console output with independently rotating detailed file logs."""
import copy
import logging
from logging.handlers import RotatingFileHandler


class ConsoleFilter(logging.Filter):
    def __init__(self, mode):
        super().__init__()
        self.mode = mode

    def filter(self, record):
        if self.mode == 'verbose':
            return True
        if self.mode == 'warning':
            return record.levelno >= logging.WARNING
        return record.levelno >= logging.WARNING or getattr(record, 'console', False)


class ConsoleFormatter(logging.Formatter):
    def format(self, record):
        # Full traceback remains in bot.log, not the terminal scrollback.
        brief = copy.copy(record)
        brief.exc_info = None
        brief.exc_text = None
        brief.stack_info = None
        return super().format(brief)


def configure_logging(root, storage, mode='summary'):
    console = logging.StreamHandler()
    console.addFilter(ConsoleFilter(mode))
    console.setFormatter(ConsoleFormatter('%(asctime)s %(levelname)s %(message)s'))
    file_handler = RotatingFileHandler(root / 'bot.log', maxBytes=storage['log_max_mb'] * 1024 * 1024,
                                       backupCount=storage['log_backups'], encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger = logging.getLogger('ustc')
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.addHandler(console)
    logger.addHandler(file_handler)
