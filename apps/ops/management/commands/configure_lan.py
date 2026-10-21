"""Update ALLOWED_HOSTS and CSRF origins in an existing environment file.

Does not rotate SECRET_KEY and does not print secret values.
"""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from config.ops.envfile import EnvFileError, apply_lan_address


class Command(BaseCommand):
    help = 'Set the factory LAN host in an existing production environment file.'

    def add_arguments(self, parser):
        parser.add_argument('--env-file', required=True)
        parser.add_argument('--lan', required=True)
        parser.add_argument('--hostname', default='')
        parser.add_argument('--port', type=int, default=8000)
        parser.add_argument('--https', action='store_true')

    def handle(self, *args, **options):
        path = Path(options['env_file'])
        if not path.is_file():
            raise CommandError(f'Environment file does not exist: {path}')
        original = path.read_text(encoding='utf-8')
        try:
            updated = apply_lan_address(
                original,
                lan=options['lan'],
                hostname=options['hostname'],
                port=options['port'],
                https=options['https'],
            )
        except EnvFileError as exc:
            raise CommandError(str(exc)) from exc
        path.write_text(updated, encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Updated hosts in {path}. SECRET_KEY was left unchanged.'))
