"""Uploaded files stay behind the login and the factory scope."""

import pytest
from django.http import Http404
from django.test import Client, override_settings

from apps.accounts.models import User
from apps.factories.models import Factory
from config.media_access import resolve_media_file, user_can_read_media


def _write(root, relative, payload=b'photo-bytes'):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


@pytest.mark.django_db
def test_qc_photo_is_limited_to_the_same_factory(client, factory, tmp_path):
    other = Factory.objects.create(name='Other Factory')
    operator = User.objects.create_user(
        username='media_operator',
        password='Password123!',
        role=User.Role.OPERATOR,
        factory=factory,
    )
    outsider = User.objects.create_user(
        username='media_outsider',
        password='Password123!',
        role=User.Role.QC,
        factory=other,
    )
    admin = User.objects.create_user(
        username='media_admin',
        password='Password123!',
        role=User.Role.ADMIN,
        factory=None,
    )
    relative = f'qc/{factory.id}/shot.jpg'
    _write(tmp_path, relative)
    _write(tmp_path, 'notes/private.txt', b'secret-note')

    with override_settings(MEDIA_ROOT=tmp_path):
        anonymous = Client().get(f'/media/{relative}')
        assert anonymous.status_code == 302
        assert '/accounts/login/' in anonymous['Location']

        client.force_login(operator)
        allowed = client.get(f'/media/{relative}')
        assert allowed.status_code == 200
        assert allowed.content == b'photo-bytes'

        denied_other = client.get(f'/media/qc/{other.id}/shot.jpg')
        assert denied_other.status_code == 403

        denied_note = client.get('/media/notes/private.txt')
        assert denied_note.status_code == 403

        client.force_login(outsider)
        cross = client.get(f'/media/{relative}')
        assert cross.status_code == 403

        client.force_login(admin)
        platform = client.get(f'/media/{relative}')
        assert platform.status_code == 200
        note = client.get('/media/notes/private.txt')
        assert note.status_code == 200
        assert b'secret-note' in note.content


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
