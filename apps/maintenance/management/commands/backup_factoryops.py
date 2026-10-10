import os

from django.core.management.base import BaseCommand, CommandError

from scripts.backup_factoryops import (
    configured_targets,
    create_backup,
    default_backup_root,
)


class Command(BaseCommand):
    help = (
        'Create a timestamped SQLite and media backup from the configured '
        'database and MEDIA_ROOT. Does not modify the live database.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--destination',
            default='',
            help=(
                'Folder that will contain timestamped backup directories. '
                'Defaults to FACTORYOPS_BACKUP_DIR or the user profile FactoryOpsBackups folder.'
            ),
        )
        parser.add_argument(
            '--retention-days',
            type=int,
            default=None,
            help='Remove backup folders in the destination older than this many days. Default 14.',
        )

    def handle(self, *args, **options):
        retention = options['retention_days']
        if retention is None:
            raw = os.environ.get('FACTORYOPS_BACKUP_RETENTION_DAYS', '').strip()
            try:
                retention = int(raw) if raw else 14
            except ValueError as exc:
                raise CommandError('retention-days must be an integer.') from exc
        if retention < 1:
            raise CommandError('retention-days must be at least 1.')
        destination = options['destination'] or default_backup_root()
        try:
            targets = configured_targets()
            result = create_backup(
                targets['database'],
                targets['media'],
                destination,
                retention,
                application_root=targets['application_root'],
                database_engine=targets['engine'],
            )
        except Exception as exc:
            raise CommandError(f'BACKUP FAILED: {exc}') from exc
        self.stdout.write(f'Database: {targets["database"]}')
        self.stdout.write(f'Engine: {targets["engine"]}')
        self.stdout.write(result['media_message'])
        self.stdout.write(f'BACKUP OK {result["bundle"]}')
        for path in result['removed']:
            self.stdout.write(f'PRUNED {path}')
