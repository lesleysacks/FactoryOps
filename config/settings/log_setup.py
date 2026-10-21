"""File logging for the factory PC. No network handlers."""

from pathlib import Path


def build_logging(log_dir: Path, *, max_bytes: int = 5 * 1024 * 1024, backup_count: int = 5) -> dict:
    """Rotating log configuration. Creates the directory or raises OSError."""
    log_dir.mkdir(parents=True, exist_ok=True)
    filename = str(log_dir / 'factoryops.log')
    return {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '{asctime} {levelname} {name} {message}',
                'style': '{',
            },
        },
        'handlers': {
            'factoryops_file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': filename,
                'maxBytes': max_bytes,
                'backupCount': backup_count,
                'formatter': 'verbose',
                'encoding': 'utf-8',
            },
        },
        'root': {
            'handlers': ['factoryops_file'],
            'level': 'INFO',
        },
        'loggers': {
            'django.request': {
                'handlers': ['factoryops_file'],
                'level': 'WARNING',
                'propagate': False,
            },
            'django.security': {
                'handlers': ['factoryops_file'],
                'level': 'WARNING',
                'propagate': False,
            },
            'factoryops': {
                'handlers': ['factoryops_file'],
                'level': 'INFO',
                'propagate': False,
            },
        },
    }
