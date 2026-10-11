"""
Assign V1 pilot roles and responsibilities to existing staff.

This command never creates users, never sets a password, never grants
superuser, and never changes a factory or assigned machines.

Dry-run is the default and writes nothing:

    python manage.py assign_pilot_staff

Apply only after every name matches exactly one existing user:

    python manage.py assign_pilot_staff --apply

Match rule: username, first name, or last name equals the person's name.
A partial name is not a match. Two matches are ambiguous and block apply.

After apply, an administrator sets Lesley's printing machines on the user
in Django Admin (Users → assigned machines). Re-running apply is safe.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.accounts.access import (
    INVENTORY,
    PRINTING_STATION,
    RESPONSIBILITY_GROUPS,
    RESPONSIBILITY_LABELS,
    ensure_responsibility_groups,
)
from apps.accounts.models import Role


User = get_user_model()

PILOT_ASSIGNMENTS = (
    {
        'label': 'Lesley',
        'role': Role.OPERATOR,
        'groups': (PRINTING_STATION,),
        'note': 'Operator and Head of Printing Station. Assign printing machines in Admin.',
    },
    {
        'label': 'Neville',
        'role': Role.OPERATOR,
        'groups': (INVENTORY,),
        'note': 'Operator and Inventory. Not a printing-station operator.',
    },
    {
        'label': 'Yolandi',
        'role': Role.QC,
        'groups': (),
        'note': 'Quality control only. Do not grant the Operator role.',
    },
    {
        'label': 'Frankie',
        'role': Role.SUPERVISOR,
        'groups': (),
        'note': 'Supervisor. Must not be a Django superuser.',
    },
)


def _matches(label):
    return list(
        User.objects.filter(
            Q(username__iexact=label)
            | Q(first_name__iexact=label)
            | Q(last_name__iexact=label)
        ).distinct().order_by('pk')
    )


def plan_pilot_assignments():
    people = []
    for spec in PILOT_ASSIGNMENTS:
        matches = _matches(spec['label'])
        entry = {
            'label': spec['label'],
            'planned_role': spec['role'],
            'planned_groups': [
                RESPONSIBILITY_LABELS[code] for code in spec['groups']
            ],
            'note': spec['note'],
            'status': 'missing',
            'username': '',
            'user_id': None,
            'current_role': '',
            'factory': '',
            'is_superuser': False,
            'candidates': [],
            'manual': [],
        }
        if len(matches) > 1:
            entry['status'] = 'ambiguous'
            entry['candidates'] = [user.username for user in matches]
            entry['manual'].append('More than one account matches. Choose the account by hand.')
        elif len(matches) == 1:
            user = matches[0]
            entry['username'] = user.username
            entry['user_id'] = user.pk
            entry['current_role'] = user.role
            entry['is_superuser'] = user.is_superuser
            entry['factory'] = user.factory.name if user.factory_id else ''
            if user.is_superuser:
                entry['status'] = 'blocked'
                entry['manual'].append(
                    'This account is a superuser. The command will not change that.'
                )
            else:
                entry['status'] = 'resolved'
                if not user.factory_id:
                    entry['manual'].append(
                        'No factory is set. The command will not guess one.'
                    )
                if spec['label'] == 'Lesley':
                    entry['manual'].append(
                        'Assigned printing machines are not changed. Set them in Admin.'
                    )
        else:
            entry['manual'].append(
                'No account has this exact username, first name, or last name.'
            )
        people.append(entry)
    return {
        'people': people,
        'can_apply': all(person['status'] == 'resolved' for person in people),
        'applied': False,
    }


def apply_pilot_assignments():
    plan = plan_pilot_assignments()
    if not plan['can_apply']:
        return plan
    with transaction.atomic():
        locked = []
        for entry in plan['people']:
            user = User.objects.select_for_update().get(pk=entry['user_id'])
            if user.is_superuser:
                entry['status'] = 'blocked'
                entry['manual'].append(
                    'This account is a superuser. The command will not change that.'
                )
                plan['can_apply'] = False
                return plan
            locked.append(user)
        groups = ensure_responsibility_groups()
        for spec, user in zip(PILOT_ASSIGNMENTS, locked):
            if user.role != spec['role']:
                user.role = spec['role']
                user.save(update_fields=['role'])
            desired = set(spec['groups'])
            for code in RESPONSIBILITY_GROUPS:
                group = groups[code]
                if code in desired:
                    user.groups.add(group)
                else:
                    user.groups.remove(group)
        plan['applied'] = True
    return plan


def render_plan(plan):
    lines = [
        'FactoryOps V1 pilot assignment',
        'Mode: apply' if plan.get('applied') else 'Mode: dry-run (no accounts were changed)',
        'The command does not create users, set passwords, or grant superuser.',
    ]
    for person in plan['people']:
        lines.append(
            f"{person['label']}: {person['status']}"
            + (f" username={person['username']}" if person['username'] else '')
        )
        if person['current_role']:
            lines.append(
                f"  role {person['current_role']} -> {person['planned_role']}"
                f" factory={person['factory'] or 'unset'}"
                f" superuser={person['is_superuser']}"
            )
        else:
            lines.append(f"  planned role {person['planned_role']}")
        if person['planned_groups']:
            lines.append('  responsibility: ' + ', '.join(person['planned_groups']))
        else:
            lines.append('  responsibility: none')
        if person['candidates']:
            lines.append('  candidates: ' + ', '.join(person['candidates']))
        for note in person['manual']:
            lines.append(f'  needs confirmation: {note}')
        lines.append(f"  {person['note']}")
    if plan.get('applied'):
        lines.append('Applied. Set Lesley\'s printing machines in Admin if they are still empty.')
    elif plan['can_apply']:
        lines.append('Dry-run only. Re-run with --apply to write roles and responsibilities.')
    else:
        lines.append('Not applied. Resolve every line above before using --apply.')
    return '\n'.join(lines)


class Command(BaseCommand):
    help = (
        'Dry-run or apply V1 pilot roles for Lesley, Neville, Yolandi, and Frankie. '
        'Matches existing accounts only. Does not create users or set passwords.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Write roles and responsibility groups. Refused when any person is unresolved.',
        )

    def handle(self, *args, **options):
        if options['apply']:
            plan = apply_pilot_assignments()
        else:
            plan = plan_pilot_assignments()
        self.stdout.write(render_plan(plan))
        if options['apply'] and not plan['applied']:
            raise CommandError('Pilot assignment was not applied. No accounts were changed.')
