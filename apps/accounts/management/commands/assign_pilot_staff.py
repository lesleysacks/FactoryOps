"""
Assign V1 pilot roles and responsibilities to existing staff.

This command never creates users, never sets a password, never grants
superuser, and never changes a factory, staff flag, or assigned machines.

Dry-run is the default and writes nothing:

    python manage.py assign_pilot_staff

Apply only after every exact username exists and is not a superuser:

    python manage.py assign_pilot_staff --apply

Match rule: case-sensitive username. The accounts are Lesley, Neville,
Yolandi, and Frankie. Username lesley is a different person and is never
selected. A first name or last name is not a match.

After apply, an administrator sets Lesley's printing machines on the user
in Django Admin (Users → assigned machines). Re-running apply is safe.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.access import (
    INVENTORY,
    PRINTING_STATION,
    RESPONSIBILITY_GROUPS,
    RESPONSIBILITY_LABELS,
    ensure_responsibility_groups,
)
from apps.accounts.models import Role


User = get_user_model()

# The administrator account. Case-sensitive, so this is not the operator Lesley.
PROTECTED_USERNAME = 'lesley'

PILOT_ASSIGNMENTS = (
    {
        'username': 'Lesley',
        'role': Role.OPERATOR,
        'groups': (PRINTING_STATION,),
        'note': 'Operator and Head of Printing Station. Assign printing machines in Admin.',
    },
    {
        'username': 'Neville',
        'role': Role.OPERATOR,
        'groups': (INVENTORY,),
        'note': 'Operator and Inventory. Not a printing-station operator.',
    },
    {
        'username': 'Yolandi',
        'role': Role.QC,
        'groups': (),
        'note': 'Quality control only. Do not grant the Operator role.',
    },
    {
        'username': 'Frankie',
        'role': Role.SUPERVISOR,
        'groups': (),
        'note': 'Supervisor. Must not be a Django superuser.',
    },
)


def _exact_username_matches(username):
    """Case-sensitive username match. A different capitalisation is ignored."""
    return [
        user for user in User.objects.filter(username=username).order_by('pk')
        if user.username == username
    ]


def _blank_entry(spec):
    return {
        'label': spec['username'],
        'username': '',
        'planned_role': spec['role'],
        'planned_groups': [
            RESPONSIBILITY_LABELS[code] for code in spec['groups']
        ],
        'note': spec['note'],
        'status': 'missing',
        'user_id': None,
        'current_role': '',
        'factory': '',
        'is_superuser': False,
        'candidates': [],
        'manual': [],
    }


def _remember_protected_account(entry, username):
    if username == 'Lesley' and User.objects.filter(username=PROTECTED_USERNAME).exists():
        entry['manual'].append(
            f'Username {PROTECTED_USERNAME} is a different account and was not selected.'
        )


def plan_pilot_assignments():
    people = []
    for spec in PILOT_ASSIGNMENTS:
        username = spec['username']
        matches = _exact_username_matches(username)
        entry = _blank_entry(spec)
        _remember_protected_account(entry, username)
        if len(matches) > 1:
            entry['status'] = 'ambiguous'
            entry['candidates'] = [user.username for user in matches]
            entry['manual'].append(
                'More than one account has this exact username. '
                'The command will not choose one.'
            )
        elif len(matches) == 1:
            user = matches[0]
            entry['username'] = user.username
            entry['user_id'] = user.pk
            entry['current_role'] = user.role
            entry['is_superuser'] = user.is_superuser
            entry['factory'] = user.factory.name if user.factory_id else ''
            if user.is_superuser or user.username == PROTECTED_USERNAME:
                entry['status'] = 'blocked'
                entry['manual'].append(
                    'This account is protected. The command will not change it.'
                )
            else:
                entry['status'] = 'resolved'
                if not user.factory_id:
                    entry['manual'].append(
                        'No factory is set. The command will not guess one.'
                    )
                if username == 'Lesley':
                    entry['manual'].append(
                        'Assigned printing machines are not changed. Set them in Admin.'
                    )
        else:
            entry['manual'].append(
                'No account has this exact case-sensitive username.'
            )
        people.append(entry)
    return {
        'people': people,
        'can_apply': all(person['status'] == 'resolved' for person in people),
        'applied': False,
    }


def _reject_locked_user(entry, user):
    if user.username != entry['username']:
        entry['status'] = 'blocked'
        entry['manual'].append('The account username changed before apply.')
        return True
    if user.is_superuser or user.username == PROTECTED_USERNAME:
        entry['status'] = 'blocked'
        entry['is_superuser'] = user.is_superuser
        entry['manual'].append(
            'This account is protected. The command will not change it.'
        )
        return True
    return False


def apply_pilot_assignments():
    plan = plan_pilot_assignments()
    if not plan['can_apply']:
        return plan
    with transaction.atomic():
        locked = []
        for entry in plan['people']:
            try:
                user = User.objects.select_for_update().get(pk=entry['user_id'])
            except User.DoesNotExist:
                entry['status'] = 'missing'
                entry['manual'].append(
                    'The account disappeared before apply. Nothing was written.'
                )
                plan['can_apply'] = False
                transaction.set_rollback(True)
                return plan
            if _reject_locked_user(entry, user):
                plan['can_apply'] = False
                transaction.set_rollback(True)
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


MATCH_RULE = (
    'Matching is the exact case-sensitive username '
    'Lesley, Neville, Yolandi, or Frankie. '
    'Username lesley is never selected. '
    'A first name or last name is not a match.'
)

NEXT_STEPS = (
    'Next steps: create any missing username in Admin, '
    'set each factory, re-run this dry-run, then run --apply, '
    'then assign Lesley\'s printing machines in Admin. '
    'Do not change the lesley administrator here.'
)


def unresolved_people(plan):
    return [
        person for person in plan['people'] if person['status'] != 'resolved'
    ]


def apply_refusal_message(plan):
    unresolved = unresolved_people(plan)
    if not unresolved:
        return 'Pilot assignment was not applied. No accounts were changed.'
    details = ', '.join(
        f"{person['label']} ({person['status']})" for person in unresolved
    )
    return (
        'Pilot assignment was not applied. No accounts were changed. '
        f'Unresolved: {details}. {MATCH_RULE} '
        'Accounts must already exist; this command does not create users.'
    )


def render_plan(plan):
    lines = [
        'FactoryOps V1 pilot assignment',
        'Mode: apply' if plan.get('applied') else 'Mode: dry-run (no accounts were changed)',
        'The command does not create users, set passwords, or grant superuser.',
        MATCH_RULE,
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
    missing = [person['label'] for person in plan['people'] if person['status'] == 'missing']
    if missing:
        lines.append(
            'Missing accounts: ' + ', '.join(missing) + '. '
            'Create those exact usernames in Django Admin first. '
            'This command will not invent users.'
        )
    if plan.get('applied'):
        lines.append('Applied. Set Lesley\'s printing machines in Admin if they are still empty.')
    elif plan['can_apply']:
        lines.append('Dry-run only. Re-run with --apply to write roles and responsibilities.')
    else:
        lines.append('Not applied. Resolve every line above before using --apply.')
        lines.append(NEXT_STEPS)
    return '\n'.join(lines)


class Command(BaseCommand):
    help = (
        'Dry-run or apply V1 pilot roles for usernames Lesley, Neville, '
        'Yolandi, and Frankie. Does not create users, set passwords, '
        'or change the lesley administrator.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Write roles and responsibility groups. Refused when any username is unsafe.',
        )

    def handle(self, *args, **options):
        if options['apply']:
            plan = apply_pilot_assignments()
        else:
            plan = plan_pilot_assignments()
        self.stdout.write(render_plan(plan))
        if options['apply'] and not plan['applied']:
            raise CommandError(apply_refusal_message(plan))
