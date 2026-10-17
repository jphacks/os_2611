#!/usr/bin/env python3
"""Bounded read-only hardware and installed-tool metadata; no usage-history scan."""
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

COMMANDS = ('codex', 'claude', 'git', 'python3', 'node', 'npm', 'uv', 'brew',
            'code', 'cursor', 'ffmpeg', 'pandoc', 'libreoffice', 'docker')
APP_TERMS = ('codex', 'chatgpt', 'claude', 'visual studio code', 'cursor', 'windsurf',
             'word', 'excel', 'powerpoint', 'pages', 'numbers', 'keynote', 'libreoffice',
             'notion', 'obsidian', 'slack', 'teams', 'zoom', 'chrome', 'safari', 'firefox',
             'figma', 'canva', 'adobe', 'photoshop', 'illustrator', 'premiere', 'after effects',
             'davinci', 'blender', 'comfyui', 'final cut', 'motion')


def read_os_value(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=3)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def installed_apps(directories):
    names = set()
    for folder in directories:
        try:
            for entry in folder.iterdir():
                if entry.suffix == '.app' and any(re.search(r'(?<![a-z])' + re.escape(term) + r'(?![a-z])', entry.stem.casefold()) for term in APP_TERMS):
                    names.add(entry.stem)
        except OSError:
            pass
    return sorted(names)


def collect(root=None):
    root = Path(root or Path.cwd())
    system = platform.system()
    hardware = {'os': system, 'architecture': platform.machine(), 'cpu_cores': os.cpu_count()}
    try:
        hardware['ram_bytes'] = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
    except (AttributeError, OSError, ValueError):
        hardware['ram_bytes'] = None
    try:
        disk = shutil.disk_usage(root)
        hardware['workspace_disk_free_bytes'] = disk.free
    except OSError:
        hardware['workspace_disk_free_bytes'] = None
    apps = []
    if system == 'Darwin':
        hardware['os_version'] = read_os_value(['/usr/bin/sw_vers', '-productVersion'])
        hardware['cpu_model'] = read_os_value(['/usr/sbin/sysctl', '-n', 'machdep.cpu.brand_string'])
        # sysctl memory size is more portable on macOS than SC_PHYS_PAGES.
        ram = read_os_value(['/usr/sbin/sysctl', '-n', 'hw.memsize'])
        if ram and ram.isdigit(): hardware['ram_bytes'] = int(ram)
        apps = installed_apps([Path('/Applications'), Path.home() / 'Applications', Path('/System/Applications')])
    else:
        hardware['os_version'] = platform.release()
    found = [name for name in COMMANDS if shutil.which(name)]
    return {'execution_scope': 'current_execution_environment', 'hardware': hardware, 'installed_commands': found, 'installed_apps': apps,
            'frequent_tools': None,
            'evidence': {'hardware': 'OS metadata', 'installed_commands': 'PATH lookup, no binary execution',
                         'installed_apps': 'names matching known work tools in standard macOS application directories'},
            'limitations': ['Verify this execution environment is the user computer before attributing hardware to the user.',
                            'Installed does not imply used frequently.',
                            'No usage history, processes, document content, credentials, serial number or device UUID read.',
                            'App detection is a bounded partial inventory; absence does not prove not installed.',
                            'GPU/VRAM and Windows/Linux desktop applications are not assessed.',
                            'No installation, configuration change, background job or network request performed.']}


if __name__ == '__main__':
    print(json.dumps(collect(), ensure_ascii=False))
