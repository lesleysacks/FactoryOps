"""Uploaded files stay behind the login, the role, and the factory scope."""

import pytest
from django.http import Http404
from django.test import Client, override_settings

from apps.accounts.access import INVENTORY, ensure_responsibility_groups
from apps.accounts.models import Role, User
from apps.factories.models import Factory
from config.media_access import resolve_media_file, user_can_read_media


def _write(root, relative, payload=b'photo-bytes'):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _user(username, role, factory, *, superuser=False):
    if superuser:
        return User.objects.create_superuser(
            username=username,
            email=f'{username}@factoryops.local',
            password='Password123!',
        )
    return User.objects.create_user(
        username=username,
        password='Password123!',
        role=role,
        factory=factory,
    )


def _body(response):
    return b''.join(response.streaming_content)


@pytest.mark.django_db
def test_qc_photo_requires_qc_role_and_the_same_factory(client, factory, tmp_path):
    other = Factory.objects.create(name='Other Factory')
    operator = _user('media_operator', Role.OPERATOR, factory)
    inventory = _user('media_inventory', Role.OPERATOR, factory)
    inventory.groups.add(ensure_responsibility_groups()[INVENTORY])
    qc = _user('media_qc', Role.QC, factory)
    supervisor = _user('media_supervisor', Role.SUPERVISOR, factory)
    plant_admin = _user('media_plant_admin', Role.ADMIN, factory)
    outsider_qc = _user('media_outsider_qc', Role.QC, other)
    outsider_supervisor = _user('media_outsider_supervisor', Role.SUPERVISOR, other)
    outsider_admin = _user('media_outsider_admin', Role.ADMIN, other)
    unassigned_qc = _user('media_unassigned_qc', Role.QC, None)
    unassigned_supervisor = _user('media_unassigned_supervisor', Role.SUPERVISOR, None)
    platform_admin = _user('media_platform_admin', Role.ADMIN, None)
    platform_superuser = _user('media_platform_root', Role.ADMIN, None, superuser=True)
    plant_superuser = _user('media_plant_root', Role.ADMIN, None, superuser=True)
    plant_superuser.factory = factory
    plant_superuser.save(update_fields=['factory'])
    relative = f'qc/{factory.id}/shot.jpg'
    other_relative = f'qc/{other.id}/shot.jpg'
    _write(tmp_path, relative)
    _write(tmp_path, other_relative, b'other-photo')
    _write(tmp_path, 'notes/private.txt', b'secret-note')

    with override_settings(MEDIA_ROOT=tmp_path):
        anonymous = Client().get(f'/media/{relative}')
        assert anonymous.status_code == 302
        assert '/accounts/login/' in anonymous['Location']

        denied_users = (
            operator,
            inventory,
            outsider_qc,
            outsider_supervisor,
            outsider_admin,
            unassigned_qc,
            unassigned_supervisor,
        )
        for user in denied_users:
            client.force_login(user)
            denied = client.get(f'/media/{relative}')
            assert denied.status_code == 403, user.username

        client.force_login(operator)
        assert client.get(f'/media/{other_relative}').status_code == 403
        assert client.get('/media/notes/private.txt').status_code == 403

        for user in (qc, supervisor, plant_admin, plant_superuser):
            client.force_login(user)
            allowed = client.get(f'/media/{relative}')
            assert allowed.status_code == 200, user.username
            assert _body(allowed) == b'photo-bytes'
            assert client.get(f'/media/{other_relative}').status_code == 403, user.username
            assert client.get('/media/notes/private.txt').status_code == 403, user.username

        for user in (platform_admin, platform_superuser):
            client.force_login(user)
            own = client.get(f'/media/{relative}')
            assert own.status_code == 200, user.username
            assert _body(own) == b'photo-bytes'
            other_photo = client.get(f'/media/{other_relative}')
            assert other_photo.status_code == 200, user.username
            assert _body(other_photo) == b'other-photo'
            note = client.get('/media/notes/private.txt')
            assert note.status_code == 200, user.username
            assert _body(note) == b'secret-note'


@pytest.mark.django_db
def test_media_path_traversal_is_not_served(factory, tmp_path):
    user = User.objects.create_user(
        username='media_qc',
        password='Password123!',
        role=User.Role.QC,
        factory=factory,
    )
    root = tmp_path / 'media'
    root.mkdir()
    outside = tmp_path / 'outside-secret.txt'
    outside.write_text('do-not-serve', encoding='utf-8')
    with override_settings(MEDIA_ROOT=root):
        relative = f'qc/{factory.id}/../../outside-secret.txt'
        assert user_can_read_media(user, relative) is True
        with pytest.raises(Http404):
            resolve_media_file(relative)
        assert user_can_read_media(user, '../outside-secret.txt') is False
