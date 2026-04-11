# -*- mode: python ; coding: utf-8 -*-
# SerialMonitor PyInstaller spec file

block_cipher = None

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('终端.png', '.'),
        ('config', 'config'),
        ('utils/custom_style_dark.qss', 'utils'),
        ('utils/custom_style_light.qss', 'utils'),
    ],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'serial',
        'serial.tools',
        'serial.tools.list_ports',
        'core',
        'core.ansi',
        'core.serial_handler',
        'core.ansi_parser',
        'core.protocol',
        'ui',
        'ui.main_window',
        'ui.dialogs',
        'ui.quick_send_manager',
        'ui.quick_send_panel',
        'ui.terminal_emulator',
        'utils',
        'utils.config_manager',
        'utils.i18n',
        'utils.logger',
        'utils.theme',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'email',
        'http',
        'xml',
        'pydoc',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='SerialMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['终端.png'],
)
