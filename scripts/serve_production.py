"""Start the production WSGI server.

This is the supported factory-PC entry point. It selects production settings
before Django loads. Do not use manage.py runserver for the permanent server.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.production')


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    import django
    from django.conf import settings
    from django.core.exceptions import ImproperlyConfigured

    try:
        django.setup()
    except ImproperlyConfigured as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if settings.DEBUG:
        print('Refusing to serve because DEBUG is on.', file=sys.stderr)
        return 1

    if '--check' in argv:
        print('production configuration ok')
        return 0

    bind = os.getenv('FACTORYOPS_BIND', '0.0.0.0').strip()
    raw_port = os.getenv('FACTORYOPS_PORT', '8000').strip()
    if not bind:
        print('FACTORYOPS_BIND is empty.', file=sys.stderr)
        return 1
    try:
        port = int(raw_port)
    except ValueError:
        print('FACTORYOPS_PORT must be an integer.', file=sys.stderr)
        return 1
    if port < 1 or port > 65535:
        print('FACTORYOPS_PORT is outside 1-65535.', file=sys.stderr)
        return 1

    from waitress import serve

    from config.wsgi import application

    print(f'FactoryOps listening on {bind}:{port}', flush=True)
    serve(application, host=bind, port=port, threads=8, channel_timeout=120)
    return 0


if __name__ == '__main__':
    sys.exit(main())
