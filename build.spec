# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 - 单文件 exe"""

import sys
import os
from pathlib import Path

# 不打包 opencv/numpy — pyautogui 纯 Python 模式完全够用且无依赖

# 项目根目录（SPECPATH 是 .spec 文件所在目录）
PROJECT_ROOT = Path(SPECPATH)

# 构建 datas 列表（使用 os.path.join 确保路径正确）
datas_list = []

# Switcher 图片目录
switcher_imgs = os.path.join(str(PROJECT_ROOT), 'Switcher', 'imgs')
if os.path.isdir(switcher_imgs):
    for f in os.listdir(switcher_imgs):
        src = os.path.join(switcher_imgs, f)
        if os.path.isfile(src):
            datas_list.append((src, os.path.join('Switcher', 'imgs')))

# 默认配置
default_config = os.path.join(str(PROJECT_ROOT), 'resources', 'default_config.json')
if os.path.isfile(default_config):
    datas_list.append((default_config, 'resources'))

# 图标（如果有的话）
icon_path = os.path.join(str(PROJECT_ROOT), 'resources', 'icon.ico')
if not os.path.isfile(icon_path):
    icon_path = None

a = Analysis(
    ['main.py'],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=datas_list,
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
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test',
        'matplotlib',
        'numpy',
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
    console=True,   # pyautogui 截图依赖控制台子系统
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)
