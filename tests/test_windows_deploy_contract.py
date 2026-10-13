"""The Windows scripts stay present and keep the deployment safety rules."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WINDOWS = ROOT / 'deploy' / 'windows'

REQUIRED = [
    'FactoryOps.Common.ps1',
    'Install-FactoryOps.ps1',
    'Start-FactoryOps.ps1',
    'Stop-FactoryOps.ps1',
    'Restart-FactoryOps.ps1',
    'Get-FactoryOpsStatus.ps1',
    'Uninstall-FactoryOps.ps1',
    'Register-FactoryOpsKiosk.ps1',
    'Start-FactoryOpsKiosk.ps1',
    'Install-FactoryOpsFirewall.ps1',
    'Remove-FactoryOpsFirewall.ps1',
    'Backup-FactoryOps.ps1',
    'Restore-FactoryOps.ps1',
    'factoryops.config.example.json',
]


def _read(name):
    return (WINDOWS / name).read_text(encoding='utf-8')


def test_windows_scripts_exist_and_avoid_powershell_7_syntax():
    combined = []
    for name in REQUIRED:
        text = _read(name)
        assert text.strip()
        combined.append(text)
        assert '&&' not in text
        assert '??' not in text
        assert 'AutoAdminLogon' not in text
    everything = '\n'.join(combined)
    assert 'runserver' not in everything


def test_server_task_restarts_and_does_not_launch_a_second_copy_blindly():
    start = _read('Start-FactoryOps.ps1')
    install = _read('Install-FactoryOps.ps1')
    assert 'serve_production.py' in start
    assert 'serve_production.py' in install
    assert 'IgnoreNew' in install
    assert 'RestartCount 999' in install
    assert 'AtStartup' in install
    assert 'SYSTEM' in install
    assert 'already listening' in start or 'already running' in start


def test_destructive_scripts_ask_for_confirmation_and_keep_data():
    uninstall = _read('Uninstall-FactoryOps.ps1')
    restore = _read('Restore-FactoryOps.ps1')
    remove_firewall = _read('Remove-FactoryOpsFirewall.ps1')
    assert 'SupportsShouldProcess' in uninstall
    assert 'does not delete the database' in uninstall
    assert 'SupportsShouldProcess' in restore
    assert '--confirm' in restore
    assert 'SupportsShouldProcess' in remove_firewall
    assert 'flush' not in uninstall.lower()


def test_firewall_is_limited_to_the_private_subnet():
    firewall = _read('Install-FactoryOpsFirewall.ps1')
    assert 'Private' in firewall
    assert 'LocalSubnet' in firewall
    assert '0.0.0.0/0' in firewall
    assert 'public internet' in firewall


def test_kiosk_opens_the_login_page_without_a_stored_password():
    kiosk = _read('Start-FactoryOpsKiosk.ps1')
    register = _read('Register-FactoryOpsKiosk.ps1')
    assert '/accounts/login' in kiosk
    assert 'password=' in kiosk
    assert '--kiosk' in kiosk
    assert 'standard user' in register
    assert 'password' not in register.lower()


def test_backup_script_calls_the_sqlite_backup_tool():
    backup = _read('Backup-FactoryOps.ps1')
    source = (ROOT / 'scripts' / 'backup_factoryops.py').read_text(encoding='utf-8')
    assert 'backup_factoryops.py' in backup
    assert 'Copy-Item' not in backup
    assert '.backup(' in source
    assert 'shutil.copy' not in source.split('def copy_media', 1)[0]


def test_example_config_has_no_secrets_and_points_at_login():
    config = json.loads(_read('factoryops.config.example.json'))
    assert config['kioskUrl'].endswith('/accounts/login/')
    assert config['firewallRemoteAddress'] == 'LocalSubnet'
    assert 'secret' not in json.dumps(config).lower()
    assert config['backupDir'] != str(Path(config['projectRoot']))
    assert not config['backupDir'].startswith(config['projectRoot'] + '\\')
