"""Push pending report rows to Google Sheets.

The command is safe to schedule. When the integration is disabled it exits
successfully and does not contact Google. Source rows are never deleted.
"""

from django.core.management.base import BaseCommand, CommandError

from apps.reports.sync import run_sync


class Command(BaseCommand):
    help = 'Copy approved FactoryOps reports to Google Sheets. Disabled integrations exit without calling Google.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--retry',
            action='store_true',
            help='Reset failed rows and the backoff window, then push one batch.',
        )

    def handle(self, *args, **options):
        result = run_sync(trigger='command', ignore_backoff=options['retry'])
        self.stdout.write(result.message)
        if result.outcome in ('failed', 'partial', 'misconfigured'):
            raise CommandError(result.message)
