# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 - 单文件 exe"""

import sys
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_all

# 项目根目录
PROJECT_ROOT = Path(SPECPATH)

# 构建 datas 列表
datas_list = []
switcher_imgs = os.path.join(str(PROJECT_ROOT), 'Switcher', 'imgs')
if os.path.isdir(switcher_imgs):
    for f in os.listdir(switcher_imgs):
        src = os.path.join(switcher_imgs, f)
        if os.path.isfile(src):
            datas_list.append((src, os.path.join('Switcher', 'imgs')))

default_config = os.path.join(str(PROJECT_ROOT), 'resources', 'default_config.json')
if os.path.isfile(default_config):
    datas_list.append((default_config, 'resources'))

# collect_all 确保 numpy+opencv 的 .pyd/.dll 全部打包
_numpy = collect_all('numpy')
_cv2 = collect_all('cv2')

a = Analysis(
    ['main.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=_numpy[1] + _cv2[1],
    datas=datas_list + _numpy[0] + _cv2[0],
    hiddenimports=[
        'customtkinter',
        'darkdetect',
        'psutil',
        'requests',
        'pydirectinput',
        'pyautogui',
        'PIL',
        'PIL.Image',
        'PIL.ImageGrab',
        'core',
        'core.logger',
        'core.ai_assistant',
        'core.log_analyzer',
        'core.process_tools',
        'core.network',
        'core.dingtalk',
        'core.history',
        'core.shutdown',
        'core.task_runner',
        'core.scheduler',
        'Switcher.WwAccountSwitcher',
        'config_manager',
        'gui',
    ] + _numpy[2] + _cv2[2],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test',
        'matplotlib',
        'pandas',
        'scipy',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GameAutoDaily',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
