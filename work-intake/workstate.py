"""Local task journal. Python 3.9+, SQLite from the standard library; no daemon."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4


class WorkError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise WorkError(message)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def text(value, limit=8000):
    return isinstance(value, str) and 0 < len(value.strip()) <= limit


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class Journal:
    def __init__(self, directory):
        original = Path(directory).absolute()
        require(not original.is_symlink() and not any(p.is_symlink() and str(p) not in ('/tmp', '/var')
                for p in original.parents), 'unsafe_state_path')
        self.directory = original.resolve()
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        self.path = self.directory / 'work.sqlite3'
        require(not self.path.is_symlink(), 'unsafe_state_path')
        self.db = sqlite3.connect(str(self.path), timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA secure_delete=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS tasks (
              id TEXT PRIMARY KEY, document TEXT NOT NULL, revision INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
              seq INTEGER PRIMARY KEY AUTOINCREMENT, task TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
              id TEXT UNIQUE NOT NULL, at TEXT NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        self.db.commit()
        os.chmod(self.path, 0o600)

    def close(self):
        self.db.close()

    def load(self, task):
        row = self.db.execute('SELECT document,revision FROM tasks WHERE id=?', (task,)).fetchone()
        require(row is not None, 'unknown_task')
        result = json.loads(row['document'])
        result['revision'] = row['revision']
        return result

    def tasks(self):
        rows = self.db.execute('SELECT document,revision FROM tasks ORDER BY rowid DESC').fetchall()
        return [dict(json.loads(r['document']), revision=r['revision']) for r in rows]

    def create(self, root, goal, output, criteria):
        task = {'id': uuid4().hex[:12], 'root': str(root), 'goal': goal, 'output': output,
                'criteria': criteria, 'status': 'working', 'created_at': stamp(), 'updated_at': stamp(),
                'understanding': [], 'questions': [], 'candidates': [], 'next_actions': [],
                'grants': [], 'capabilities': [], 'completion': None}
        with self.db:
            self.db.execute('INSERT INTO tasks VALUES (?,?,0)', (task['id'], encoded(task)))
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('active', task['id']))
        self.add(task['id'], 'created', {'goal': goal, 'root': str(root)})
        return self.load(task['id'])

    def save(self, task, expected=None):
        previous = task.pop('revision')
        if expected is not None:
            require(expected == previous, 'revision_conflict')
        task['updated_at'] = stamp()
        with self.db:
            result = self.db.execute('UPDATE tasks SET document=?, revision=revision+1 WHERE id=? AND revision=?',
                                     (encoded(task), task['id'], previous))
            require(result.rowcount == 1, 'revision_conflict')
        return self.load(task['id'])

    def add(self, task, kind, payload):
        event = {'id': uuid4().hex[:16], 'at': stamp(), 'kind': kind, 'payload': payload}
        with self.db:
            self.db.execute('INSERT INTO events(task,id,at,kind,payload) VALUES (?,?,?,?,?)',
                            (task, event['id'], event['at'], kind, encoded(payload)))
        return event

    def events(self, task):
        rows = self.db.execute('SELECT id,at,kind,payload FROM events WHERE task=? ORDER BY seq', (task,)).fetchall()
        return [dict(id=r['id'], at=r['at'], kind=r['kind'], payload=json.loads(r['payload'])) for r in rows]

    def activate(self, task):
        self.load(task)
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('active', task))

    def active(self):
        row = self.db.execute('SELECT value FROM settings WHERE key=?', ('active',)).fetchone()
        return row['value'] if row else None

    def forget(self, task):
        with self.db:
            self.db.execute('DELETE FROM tasks WHERE id=?', (task,))
            self.db.execute('DELETE FROM settings WHERE key=? AND value=?', ('active', task))
        # No raw transcripts or output files are removed; SQLite backups are outside this control.
        return {'forgotten': task, 'workspace_files_removed': False}
