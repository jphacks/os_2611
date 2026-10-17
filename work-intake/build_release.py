#!/usr/bin/env python3
"""Deterministic release from allowlisted project paths, never git/private state."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import zipfile

ROOT = Path(__file__).resolve().parent
VERSION = '0.2.0'
TOP = {'AGENTS.md','CLAUDE.md','README.md','START.md','START_HERE.txt','START.command',
       'launch.py','environment.py','workflow.py','work.py','workstate.py','worktools.py',
       'build_release.py','.gitignore','LICENSE'}
DIRS = {'.agents','.claude','docs'}
SOURCE_DIRS = DIRS | {'tests','examples','research'}


def files(source=False):
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file() or p.is_symlink(): continue
        parts = p.relative_to(ROOT).parts
        if any(s in {'.private','.git','__pycache__','.DS_Store'} or s.startswith('.env') for s in parts): continue
        if p.suffix in {'.pyc','.sqlite3','.zip'}: continue
        if (len(parts)==1 and parts[0] in TOP) or parts[0] in (SOURCE_DIRS if source else DIRS): yield p


def build(destination, source=False):
    destination.mkdir(parents=True,exist_ok=True)
    path=destination/('work-intake-'+VERSION+('-source' if source else '')+'.zip')
    manifest=[]
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for p in files(source):
            raw=p.read_bytes();relative=p.relative_to(ROOT).as_posix()
            info=zipfile.ZipInfo('work-intake/'+relative,(2026,10,17,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=((stat.S_IFREG | (0o755 if p.name=='START.command' else 0o644)) << 16)
            z.writestr(info,raw)
            manifest.append({'path':relative,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        manifest_text=json.dumps({'version':VERSION,'files':manifest},ensure_ascii=False,indent=2)
        info=zipfile.ZipInfo('work-intake/MANIFEST.json',(2026,10,17,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED
        info.external_attr=(stat.S_IFREG | 0o644) << 16
        z.writestr(info,manifest_text)
    return {'path':str(path),'files':len(manifest)+1,'compressed_bytes':path.stat().st_size,
            'unpacked_bytes':sum(i['bytes'] for i in manifest)+len(manifest_text.encode()),'source':source}


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=ROOT.parent/'deliverables')
    args=parser.parse_args()
    print(json.dumps([build(args.output),build(args.output,True)],ensure_ascii=False))
