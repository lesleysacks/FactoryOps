"""Create a verified SQLite and media backup. Does not delete the live database."""

import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from config.ops.backup import create_backup


class Command(BaseCommand):
    help = 'Back up the FactoryOps database and media files, then verify the backup.'

    def add_arguments(self, parser):
        parser.add_argument('--database', default='', help='SQLite file to back up.')
        parser.add_argument('--media', default='', help='Media directory to copy.')
        parser.add_argument('--env-file', default='', help='Environment file to redact into the backup.')
        parser.add_argument('--backup-root', default='', help='Directory that holds dated backups.')
        parser.add_argument('--retention', type=int, default=0, help='Verified backups to keep. Default is 14.')
        parser.add_argument('--log', default='', help='Backup log file.')

    def handle(self, *args, **options):
        database = Path(options['database'] or settings.DATABASES['default']['NAME'])
        media = Path(options['media'] or settings.MEDIA_ROOT)
        env_file = Path(
            options['env_file']
            or os.environ.get('FACTORYOPS_ENV_FILE', '')
            or (settings.BASE_DIR / '.env')
        )
        backup_root = Path(
            options['backup_root']
            or os.environ.get('FACTORYOPS_BACKUP_DIR', '')
            or (settings.BASE_DIR / 'backups')
        )
        retention = options['retention'] or int(os.environ.get('FACTORYOPS_BACKUP_RETENTION', '14'))
        log_dir = Path(os.environ.get('FACTORYOPS_LOG_DIR', settings.BASE_DIR / 'logs'))
        log_path = Path(options['log'] or (log_dir / 'backup.log'))
        result = create_backup(
            database_path=database,
            media_root=media,
            env_file=env_file if env_file.is_file() else None,
            backup_root=backup_root,
            retention=retention,
            log_path=log_path,
        )
        if not result.verified or result.path is None:
            raise CommandError(result.message)
        self.stdout.write(self.style.SUCCESS(result.message))
