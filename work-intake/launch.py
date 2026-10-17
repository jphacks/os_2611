#!/usr/bin/env python3
"""Local launcher only. No model, credentials, installation or approval overrides."""
import argparse
import ctypes
import re
import json
import os
import plistlib
from pathlib import Path
import shutil
import subprocess
import sqlite3
import sys
from urllib.parse import urlencode


def workspace(script=None):
    here = Path(script or __file__).resolve().parent
    # Release: .launcher/launch.py beside app/. Development: launch.py in root.
    root = here.parent / 'app' if here.name == '.launcher' else here
    for required in ('AGENTS.md', 'CLAUDE.md', '.agents/skills/work-intake/scripts/intake.py'):
        if not (root / required).is_file():
            raise ValueError('incomplete_package')
    return root.resolve()


def language():
    value = os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or os.environ.get('LANG') or ''
    if sys.platform == 'darwin':
        try:
            r = subprocess.run(['/usr/bin/defaults', 'read', '-g', 'AppleLanguages'],
                               capture_output=True, text=True, timeout=3)
            if r.returncode == 0:
                match = re.search(r'["\s(,]([a-zA-Z]{2,3}(?:[-_][a-zA-Z0-9]+)*)', r.stdout)
                if match: value = match.group(1)
        except (OSError, subprocess.SubprocessError):
            pass
    value = value.split('.')[0].split('@')[0].replace('_', '-')
    return value if value.lower() not in ('', 'c', 'posix') else 'en'


def codex_available():
    """Read URL-handler registration without opening any application."""
    if sys.platform != 'darwin': return False
    try:
        cf = ctypes.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        ls = ctypes.CDLL('/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/LaunchServices')
        cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFRelease.argtypes = [ctypes.c_void_p]
        cf.CFRelease.restype = None
        ls.LSCopyDefaultHandlerForURLScheme.argtypes = [ctypes.c_void_p]
        ls.LSCopyDefaultHandlerForURLScheme.restype = ctypes.c_void_p
        scheme = cf.CFStringCreateWithCString(None, b'codex', 0x08000100)
        if not scheme: return False
        try:
            handler = ls.LSCopyDefaultHandlerForURLScheme(scheme)
            if handler: cf.CFRelease(handler)
            return bool(handler)
        finally:
            cf.CFRelease(scheme)
    except (OSError, AttributeError):
        return False


def codex_app():
    # Inspect only standard application metadata; never launch to detect.
    for base in (Path('/Applications'), Path.home() / 'Applications'):
        for name in ('Codex.app', 'ChatGPT.app'):
            app = base / name
            try:
                with (app / 'Contents/Info.plist').open('rb') as f:
                    info = plistlib.load(f)
                schemes = [s for item in info.get('CFBundleURLTypes', [])
                           for s in item.get('CFBundleURLSchemes', [])]
                if 'codex' in schemes: return str(app)
            except (OSError, ValueError, TypeError, AttributeError):
                pass
    return None


def codex_executable():
    search = os.pathsep.join(filter(None, [os.environ.get('PATH', ''),
        str(Path.home() / '.local/bin'), '/opt/homebrew/bin', '/usr/local/bin']))
    return shutil.which('codex', path=search)


def codex_detected():
    return codex_available() or bool(codex_app()) or bool(codex_executable())


def remembered_host(root):
    folder = root / '.private'
    path = folder / 'launcher.json'
    if folder.is_symlink() or path.is_symlink(): return None
    try:
        host = json.loads(path.read_text()).get('host')
        return host if host in ('codex', 'claude') else None
    except (OSError, ValueError, AttributeError):
        return None


def choose_host(available, remembered=None):
    if remembered in available: return remembered
    if len(available) == 1: return available[0]
    if not available: raise ValueError('no_host')
    return None


def save_host(root, host):
    folder = root / '.private'
    path = folder / 'launcher.json'
    if folder.is_symlink() or path.is_symlink(): return
    try:
        folder.mkdir(mode=0o700, exist_ok=True)
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, 'O_NOFOLLOW', 0), 0o600)
        with os.fdopen(fd, 'w') as out: json.dump({'host': host}, out)
    except OSError:
        pass  # An unwritable preference must not stop the product.


def remembered_workspace(root):
    """Read only this package's active task; never inspect other host histories."""
    path = root / '.private/work.sqlite3'
    if not path.is_file() or path.is_symlink() or path.parent.is_symlink(): return None
    try:
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            row = db.execute("SELECT document FROM tasks WHERE id=(SELECT value FROM settings WHERE key='active')").fetchone()
        if row:
            work_root = Path(json.loads(row[0])['root'])
            if work_root.is_dir(): return work_root.resolve()
    except (OSError, ValueError, KeyError, sqlite3.Error):
        pass
    return None


def prompt(lang, root=None, work_root=None):
    bootstrap = ('Read the assistant instructions at ' + json.dumps(str(root / 'AGENTS.md')) + '. '
                 'Assistant installation: ' + json.dumps(str(root)) + '. '
                 'Actual work directory: ' + (json.dumps(str(work_root)) if work_root else 'not yet linked; use current context/materials, do not analyze the assistant as the user task') + '. '
                 'Use its work.py controller and docs/runtime.md with absolute paths. Resume the active task first. '
                 if root else '')
    return (bootstrap + 'Read AGENTS.md and the work-intake skill; start the work assistant, not development. '
            'Give its short introduction once. Before any question, check saved local profile and '
            'actual host memory (injected context, available memory search tools, host-declared file). '
            'Check actual device/tool evidence if available. Never restart the occupation questionnaire '
            'for known facts. Ask useful concrete missing facts when necessary; skip known, asked or '
            'declined information and keep continuity. Do not require a pain point or force a generic '
            'example. With enough context research and give an initial agent/tool suggestion now. '
            'Use actual work materials, record task state and tool results through work.py. '
            'Dynamically alternate local work, public research and execution as evidence warrants. '
            'Discover real host connections and scheduling; reuse existing authorization, '
            'and verify outcomes instead of trusting a supplied receipt. Before saving personal facts '
            'ask confirmation. Follow my conversation language; Initial system language: ' + lang + '.')


def claude_executable():
    search = os.pathsep.join(filter(None, [os.environ.get('PATH', ''),
        str(Path.home() / '.local/bin'), '/opt/homebrew/bin', '/usr/local/bin']))
    return shutil.which('claude', path=search)


def plan(host, root, lang, platform=None, claude=None, codex_cli=None, desktop_app=None, work_root=None):
    platform = platform or sys.platform
    work_root = Path(work_root).resolve() if work_root else None
    actual_cwd = work_root or root
    initial = prompt(lang, root, work_root)
    if host == 'codex':
        executable = codex_cli or codex_executable()
        app = desktop_app or (codex_app() if platform == 'darwin' else None)
        if executable and not (platform == 'darwin' and (app or codex_available())):
            return {'host': host, 'cwd': str(actual_cwd), 'command': [executable, initial],
                    'prompt': initial, 'requires_send': False}
        url = 'codex://threads/new?' + urlencode({'path': str(actual_cwd), 'prompt': initial})
        if platform == 'darwin':
            return {'host': host, 'cwd': str(actual_cwd), 'command': ['/usr/bin/open'] + (['-a', app] if app else []) + [url],
                    'prompt': initial, 'requires_send': True}
        raise ValueError('mac_launcher_only')
    executable = claude or claude_executable()
    if not executable:
        raise ValueError('claude_not_installed')
    return {'host': host, 'cwd': str(actual_cwd), 'command': [executable, initial],
            'prompt': initial, 'requires_send': False}


def message(code, lang):
    messages = {
        'zh': {'incomplete_package': '文件不完整。请重新解压完整压缩包后再点启动。',
               'claude_not_installed': '没有找到 Claude Code 命令行程序。若你使用 Codex，请选择 Codex。本启动器不会替你安装软件。',
               'mac_launcher_only': '此双击启动入口适用于 Mac。',
               'open_failed': '没有成功打开应用。请确认已安装 Codex，且系统能打开 codex:// 链接。',
               'opened': '已向 Codex 发送打开请求。请在新对话中点一次“发送”，然后正常聊天。'},
        'ja': {'incomplete_package': 'ファイルが不足しています。ZIP全体を展開してから起動してください。',
               'claude_not_installed': 'Claude Codeのコマンドが見つかりません。Codexを使う場合を選んでください。ソフトの自動インストールはしません。',
               'mac_launcher_only': 'この起動ボタンはMac用です。',
               'open_failed': 'アプリを開けませんでした。Codexのインストールとcodex://リンクを確認してください。',
               'opened': 'Codexに起動を依頼しました。新しい会話で「送信」を一度押し、そのまま話してください。'},
        'en': {'incomplete_package': 'Package incomplete. Extract the entire ZIP and try again.',
               'claude_not_installed': 'Claude Code CLI was not found. Choose Codex if it is installed. No software was installed.',
               'mac_launcher_only': 'This double-click launcher is for macOS.',
               'open_failed': 'The app could not be opened. Check that Codex is installed and handles codex:// links.',
               'opened': 'Requested Codex to open. Press Send once in the new conversation, then chat normally.'}}
    extras = {
        'zh': ('未找到 Codex 或 Claude Code。请先安装并登录其中一个，再双击 START.command。', '请选择：1 Codex / 2 Claude Code（记住本次选择）：'),
        'ja': ('CodexまたはClaude Codeが見つかりません。どちらかをインストールしてログイン後、START.commandを開いてください。', '選択：1 Codex / 2 Claude Code（選択を記憶します）：'),
        'ko': ('Codex 또는 Claude Code를 찾을 수 없습니다. 하나를 설치하고 로그인한 뒤 START.command를 여세요.', '선택: 1 Codex / 2 Claude Code (선택을 기억합니다): '),
        'en': ('Codex or Claude Code was not found. Install and sign into one, then open START.command.', 'Choose: 1 Codex / 2 Claude Code (remember this choice): ')}
    base = lang.lower().replace('_', '-').split('-')[0]
    if code == 'fallback_cli':
        return {'zh': '应用启动失败，改用已安装的 Codex 命令行继续。',
                'ja': 'アプリを起動できないため、インストール済みのCodex CLIで続けます。',
                'ko': '앱을 열지 못해 설치된 Codex CLI로 계속합니다.'}.get(base,
                'App launch failed; continuing in your installed Codex CLI.')
    if code in ('no_host', 'choose_host'):
        return extras.get(base, extras['en'])[0 if code == 'no_host' else 1]
    if base == 'ko':
        korean = {'incomplete_package': '파일이 누락되었습니다. ZIP 전체를 다시 압축 해제하세요.',
                  'claude_not_installed': 'Claude Code 명령을 찾을 수 없습니다.',
                  'mac_launcher_only': '이 실행 파일은 macOS용입니다.',
                  'open_failed': '앱을 열지 못했습니다. 설치 상태를 확인하세요.',
                  'opened': 'Codex에 열기를 요청했습니다. 새 대화에서 전송을 한 번 누르고 대화하세요.'}
        return korean[code]
    return messages.get(lang.lower().replace('_', '-').split('-')[0], messages['en'])[code]


def execute(p, lang):
    """No architecture assumptions. Keep existing host approval defaults."""
    try:
        result = subprocess.run(p['command'], cwd=p['cwd'], timeout=15 if p['requires_send'] else None)
    except (OSError, subprocess.SubprocessError):
        result = subprocess.CompletedProcess(p['command'], 1)
    if result.returncode and p['requires_send']:
        cli = codex_executable()
        if cli:
            print(message('fallback_cli', lang))
            p['requires_send'] = False
            return subprocess.run([cli, p['prompt']], cwd=p['cwd'])
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', choices=['auto', 'codex', 'claude'], default='auto')
    parser.add_argument('--language')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--workdir', type=Path)
    args = parser.parse_args()
    lang = args.language or language()
    try:
        root = workspace()
        if not shutil.which('python3'):
            raise ValueError('incomplete_package')
        host = args.host
        if host == 'auto':
            available = ([] if not codex_detected() else ['codex']) + ([] if not claude_executable() else ['claude'])
            host = choose_host(available, remembered_host(root))
            if host is None:
                if args.dry_run: raise ValueError('choose_host')
                while host is None:
                    selected = input(message('choose_host', lang)).strip()
                    host = {'1': 'codex', '2': 'claude'}.get(selected)
                save_host(root, host)
        work_root = args.workdir.resolve() if args.workdir else remembered_workspace(root)
        if work_root is not None and not work_root.is_dir(): raise ValueError('incomplete_package')
        p = plan(host, root, lang, work_root=work_root)
        if args.dry_run:
            print(json.dumps(p, ensure_ascii=False))
            return 0
        result = execute(p, lang)

        if result.returncode:
            print(message('open_failed', lang))
            return 1
        if p['requires_send']: print(message('opened', lang))
        return 0
    except ValueError as exc:
        print(message(str(exc), lang))
    except (OSError, subprocess.SubprocessError, EOFError, KeyboardInterrupt):
        print(message('open_failed', lang))
    return 1


if __name__ == '__main__':
    sys.exit(main())
