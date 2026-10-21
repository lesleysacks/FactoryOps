"""Static safety checks for the Windows deployment scripts.

These scripts are not executed here. The factory PC runs them on Windows.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent / 'deploy' / 'windows'


def _text(name: str) -> str:
    return (ROOT / name).read_text(encoding='utf-8')


def test_start_script_does_not_migrate_or_use_runserver():
    text = _text('Start-FactoryOps.ps1')
    assert 'manage.py migrate' not in text
    assert 'runserver' not in text
    assert 'createsuperuser' not in text
    assert 'waitress' in text
    assert 'config.settings.production' in _text('FactoryOps.Common.ps1')
    assert 'Test-FactoryOpsHealth' in text


def test_open_script_uses_login_page_without_credentials():
    text = _text('Open-FactoryOps.ps1')
    assert '/accounts/login/' in text
    assert '/health/' in _text('FactoryOps.Common.ps1')
    assert 'SECRET_KEY' not in text
    assert '--password' not in text
    assert 'createsuperuser' not in text
    assert 'Wait-FactoryOpsHealth' in text
    assert 'FactoryOpsBrowserLauncher' in text


def test_install_keeps_existing_env_and_does_not_delete_sqlite():
    install = _text('Install-FactoryOps.ps1')
    common = _text('FactoryOps.Common.ps1')
    assert 'Keeping the existing environment file' in install
    assert 'manage.py migrate' in install
    assert 'Remove-Item' not in install
    assert '*.sqlite3' in common
    assert '.env' in common


def test_update_backs_up_before_migrate():
    text = _text('Update-FactoryOps.ps1')
    assert text.index('backup_factoryops') < text.index('manage.py migrate')
    assert 'Database file was not deleted' in text


def test_disable_does_not_delete_files():
    text = _text('Disable-FactoryOps.ps1')
    assert 'Remove-Item' not in text
    assert 'were not deleted' in text


def test_uninstall_refuses_data_deletion_without_confirmation():
    text = _text('Uninstall-FactoryOps.ps1')
    data_block = text.split('if ($DeleteData)', 1)[1]
    assert 'DELETE FACTORY DATA' in data_block
    assert data_block.index('DELETE FACTORY DATA') < data_block.index('Remove-Item')


def test_restore_test_script_does_not_pass_replace_live():
    text = _text('Test-FactoryOpsRestore.ps1')
    assert '--replace-live' not in text
    assert 'restore_factoryops' in text


def test_server_task_restarts_and_browser_task_is_separate():
    tasks = _text('FactoryOps.Tasks.ps1')
    assert 'RestartOnFailure' in tasks
    assert 'BootTrigger' in tasks
    assert 'LogonTrigger' in tasks
    assert 'S-1-5-18' in tasks
    assert 'LeastPrivilege' in tasks
