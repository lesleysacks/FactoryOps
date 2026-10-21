from django.core.management.base import BaseCommand, CommandError

from scripts.backup_factoryops import configured_targets
from scripts.verify_restore import verify_restore


class Command(BaseCommand):
    help = (
        'Validate a backup and rehearse restore on a disposable copy. '
        'Refuses the live database path and does not modify it.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--backup', required=True, help='Timestamped backup directory.')
        parser.add_argument(
            '--destination',
            default='',
            help=(
                'Empty folder for the rehearsal copy. '
                'Omit to use a temporary directory that is removed after the checks.'
            ),
        )

    def handle(self, *args, **options):
        try:
            targets = configured_targets()
            outcome = verify_restore(
                options['backup'],
                destination=options['destination'] or None,
                live_database=targets['database'],
            )
        except Exception as exc:
            raise CommandError(f'VERIFY FAILED: {exc}') from exc
        for line in outcome['messages']:
            self.stdout.write(line)
        self.stdout.write(f'VERIFY OK {outcome["destination"]}')
