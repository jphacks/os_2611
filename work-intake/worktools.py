"""Actual scoped I/O, bounded public fetch, process execution and artifact checks."""
import csv
import io
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from workstate import WorkError, require, digest, text

MAX_FILE = 2 * 1024 * 1024


def scoped(root, name):
    require(isinstance(name, str) and bool(name), 'missing_path')
    root = Path(root).resolve()
    path = (root / name).resolve()
    require(path != root and root in path.parents, 'outside_work_scope')
    relative = path.relative_to(root)
    require(not any(p in {'.git', '.private', '.env', '.ssh', '.aws'} or p.endswith('.sqlite3')
                    for p in relative.parts), 'private_path_excluded')
    return path


def read_file(root, name):
    p = scoped(root, name)
    require(p.is_file() and p.stat().st_size <= MAX_FILE, 'missing_or_large_file')
    raw = p.read_bytes()
    try:
        content = raw.decode('utf-8-sig')
    except UnicodeError:
        raise WorkError('binary_file_use_host_document_tool')
    return {'path': str(p), 'sha256': digest(raw), 'size': len(raw), 'content': content,
            'evidence_origin': 'local_file_read'}


def inspect(root, names):
    require(isinstance(names, list) and 0 < len(names) <= 40, 'invalid_paths')
    return [read_file(root, p) for p in names]


def write_file(root, name, content, expected=None):
    require(isinstance(content, str) and len(content.encode()) <= MAX_FILE, 'invalid_content')
    p = scoped(root, name)
    before = p.read_bytes() if p.is_file() else None
    require((expected is None and before is None) or (before is not None and expected == digest(before)),
            'file_changed_or_overwrite_needs_hash')
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix='.work-write-')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(content.encode('utf-8'))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return {'path': str(p), 'sha256': digest(p.read_bytes()),
            'before_sha256': digest(before) if before is not None else None,
            'before_content': before.decode('utf-8') if before is not None else None,
            'evidence_origin': 'local_atomic_write'}


def public_url(url):
    require(text(url, 4000), 'invalid_url')
    u = urlsplit(url)
    require(u.scheme == 'https' and u.hostname and not u.username and not u.password and not u.fragment,
            'public_https_required')
    require(u.port in (None, 443), 'public_https_required')
    try:
        addresses = socket.getaddrinfo(u.hostname, 443, type=socket.SOCK_STREAM)
    except OSError:
        raise WorkError('network_or_dns_unavailable_use_host_search')
    require(addresses and all(ipaddress.ip_address(a[4][0]).is_global for a in addresses),
            'non_public_destination')
    return url


class PublicRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    public_url(url)
    opener = build_opener(PublicRedirects())
    request = Request(url, headers={'User-Agent': 'WorkIntake/0.2 (public research)', 'Accept-Encoding': 'identity'})
    try:
        with opener.open(request, timeout=15) as response:
            raw = response.read(MAX_FILE + 1)
            require(len(raw) <= MAX_FILE, 'response_too_large')
            encoding = response.headers.get_content_charset() or 'utf-8'
            content = raw.decode(encoding, errors='replace')
            return {'url': response.url, 'status_code': response.status, 'sha256': digest(raw),
                    'content': content, 'bytes': len(raw), 'evidence_origin': 'direct_https_fetch'}
    except (OSError, ValueError) as exc:
        if isinstance(exc, WorkError): raise
        raise WorkError('fetch_failed_use_host_search')


def run(root, argv, timeout=30):
    require(isinstance(argv, list) and 0 < len(argv) <= 100 and all(text(x, 100000) for x in argv), 'invalid_argv')
    require(type(timeout) is int and 1 <= timeout <= 45, 'invalid_timeout')
    start = time.monotonic()
    # The process inherits host OS permissions. cwd is NOT a security sandbox.
    # Arbitrary user-approved commands may have side effects beyond tracked files.
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        p = subprocess.Popen(argv, cwd=root, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                             start_new_session=(os.name == 'posix'))
        timed_out = False
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == 'posix': os.killpg(p.pid, signal.SIGKILL)
            else: p.kill()
            p.wait()
        out.seek(0); err.seek(0)
        stdout, stderr = out.read(32769), err.read(32769)
    return {'argv': argv, 'cwd': str(root), 'returncode': p.returncode, 'timed_out': timed_out,
            'stdout': stdout[:32768].decode('utf-8', errors='replace'),
            'stderr': stderr[:32768].decode('utf-8', errors='replace'),
            'truncated': len(stdout) > 32768 or len(stderr) > 32768,
            'duration_seconds': round(time.monotonic() - start, 4), 'evidence_origin': 'local_subprocess'}


def verify(root, checks):
    require(isinstance(checks, list) and 0 < len(checks) <= 40, 'invalid_checks')
    results = []
    for c in checks:
        require(isinstance(c, dict) and set(c) <= {'path', 'sha256', 'contains', 'csv_columns', 'csv_rows'}, 'invalid_check')
        require(any(k in c for k in ('sha256', 'contains', 'csv_columns', 'csv_rows')), 'vacuous_check')
        observed = read_file(root, c['path'])
        passed = True
        if 'sha256' in c: passed = passed and c['sha256'] == observed['sha256']
        if 'contains' in c:
            require(isinstance(c['contains'], list) and c['contains'] and all(text(s) for s in c['contains']), 'invalid_check')
            passed = passed and all(s in observed['content'] for s in c['contains'])
        if 'csv_columns' in c or 'csv_rows' in c:
            reader = csv.DictReader(io.StringIO(observed['content']))
            rows = list(reader)
            if 'csv_columns' in c: passed = passed and reader.fieldnames == c['csv_columns']
            if 'csv_rows' in c: passed = passed and rows == c['csv_rows']
        results.append({'path': observed['path'], 'sha256': observed['sha256'], 'passed': passed,
                        'checks': {k: v for k, v in c.items() if k != 'path'}})
    return {'passed': all(r['passed'] for r in results), 'checks': results,
            'evidence_origin': 'independent_local_artifact_read',
            'limitation': 'Checks are caller-selected; this verifies their assertions, not open-ended semantic quality.'}
