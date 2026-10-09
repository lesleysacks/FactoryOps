"""Restore a verified backup into a chosen directory.

By default this refuses to write the live database. Use a temporary --target
to test a restore. --replace-live is only for a stopped server.
"""

import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from config.ops.backup import restore_backup


class Command(BaseCommand):
    help = 'Restore a verified FactoryOps backup into a target directory.'

    def add_arguments(self, parser):
        parser.add_argument('--backup', required=True, help='Verified backup directory.')
        parser.add_argument('--target', required=True, help='Directory to receive the restored files.')
        parser.add_argument(
            '--replace-live',
            action='store_true',
            help='Allow the target to be the live database path. Stop the server first.',
        )
        parser.add_argument('--log', default='')

    def handle(self, *args, **options):
        log_dir = Path(os.environ.get('FACTORYOPS_LOG_DIR', settings.BASE_DIR / 'logs'))
        log_path = Path(options['log'] or (log_dir / 'backup.log'))
        result = restore_backup(
            backup_dir=Path(options['backup']),
            target_dir=Path(options['target']),
            live_database_path=Path(settings.DATABASES['default']['NAME']),
            live_media_root=Path(settings.MEDIA_ROOT),
            replace_live=options['replace_live'],
            log_path=log_path,
        )
        if not result.verified or result.path is None:
            raise CommandError(result.message)
        self.stdout.write(self.style.SUCCESS(result.message))
