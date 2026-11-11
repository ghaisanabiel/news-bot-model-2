import json
import sqlite3
from contextlib import contextmanager
from .config import now
from .models import Story, duplicate, fingerprint


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.db() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS stories (
                    id INTEGER PRIMARY KEY, fingerprint TEXT UNIQUE, version INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'candidate', body TEXT NOT NULL,
                    draft TEXT, package TEXT, created TEXT NOT NULL, checked TEXT NOT NULL,
                    sent_day TEXT, note TEXT NOT NULL DEFAULT '');
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY, key TEXT UNIQUE, kind TEXT, story_id INTEGER,
                    version INTEGER, payload TEXT, status TEXT DEFAULT 'pending');
                CREATE TABLE IF NOT EXISTS calls (id INTEGER PRIMARY KEY, day TEXT, kind TEXT, tokens INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, at TEXT, event TEXT, detail TEXT);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key, default=''):
        with self.db() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
            return row[0] if row else default

    def set(self, key, value):
        with self.db() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, str(value)))

    def log(self, event, detail):
        with self.db() as db:
            db.execute('INSERT INTO audit(at,event,detail) VALUES (?,?,?)', (now().isoformat(), event, detail))

    def add(self, story):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT body FROM stories ORDER BY id DESC LIMIT 500').fetchall()
            if any(duplicate(story, Story.model_validate_json(r[0])) for r in rows):
                return None
            stamp = now().isoformat()
            row = db.execute('INSERT OR IGNORE INTO stories(fingerprint,body,created,checked) VALUES (?,?,?,?)',
                             (fingerprint(story), story.model_dump_json(), stamp, stamp))
            return row.lastrowid if row.rowcount else None

    def story(self, ident):
        with self.db() as db:
            row = db.execute('SELECT * FROM stories WHERE id=?', (ident,)).fetchone()
            return dict(row) if row else None

    def update(self, ident, **values):
        allowed = {'status', 'version', 'body', 'draft', 'package', 'checked', 'sent_day', 'note'}
        if not values.keys() <= allowed:
            raise ValueError('Invalid fields')
        with self.db() as db:
            db.execute('UPDATE stories SET ' + ','.join(f'{k}=?' for k in values) + ' WHERE id=?',
                       (*values.values(), ident))

    def candidates(self):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM stories WHERE status='candidate' AND sent_day IS NULL ORDER BY json_extract(body,'$.score') DESC,id DESC")]

    def transition(self, ident, expected_version, statuses, **values):
        allowed = {'status', 'version', 'body', 'draft', 'package', 'checked', 'sent_day', 'note'}
        if not values.keys() <= allowed:
            raise ValueError('Invalid fields')
        with self.db() as db:
            query = ('UPDATE stories SET ' + ','.join(f'{k}=?' for k in values)
                     + ' WHERE id=? AND version=? AND status IN (' + ','.join('?' for _ in statuses) + ')')
            return bool(db.execute(query, (*values.values(), ident, expected_version, *statuses)).rowcount)

    def sent_today(self):
        with self.db() as db:
            return db.execute('SELECT count(*) FROM stories WHERE sent_day=?', (now().date().isoformat(),)).fetchone()[0]

    def reserve_call(self, kind, limit):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            day = now().date().isoformat()
            count = db.execute('SELECT count(*) FROM calls WHERE day=?', (day,)).fetchone()[0]
            if count >= limit:
                raise ValueError('Batas panggilan AI harian tercapai. Coba lagi besok atau ubah AI_CALL_LIMIT.')
            return db.execute('INSERT INTO calls(day,kind) VALUES (?,?)', (day, kind)).lastrowid

    def tokens(self, call_id, count):
        with self.db() as db:
            db.execute('UPDATE calls SET tokens=? WHERE id=?', (count, call_id))

    def usage(self):
        with self.db() as db:
            return tuple(db.execute('SELECT count(*),coalesce(sum(tokens),0) FROM calls WHERE day=?', (now().date().isoformat(),)).fetchone())

    def enqueue(self, key, kind, ident=0, version=0, payload=''):
        with self.db() as db:
            return bool(db.execute('INSERT OR IGNORE INTO jobs(key,kind,story_id,version,payload) VALUES (?,?,?,?,?)',
                                   (key, kind, ident, version, payload)).rowcount)

    def claim(self):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute("SELECT * FROM jobs WHERE status='pending' ORDER BY id LIMIT 1").fetchone()
            if row:
                db.execute("UPDATE jobs SET status='running' WHERE id=?", (row['id'],))
                return dict(row)

    def finish(self, ident, status='done'):
        with self.db() as db:
            db.execute('UPDATE jobs SET status=? WHERE id=?', (status, ident))

    def recover(self):
        with self.db() as db:
            count = db.execute("UPDATE jobs SET status='interrupted' WHERE status='running'").rowcount
            db.execute("UPDATE stories SET status=CASE WHEN draft IS NOT NULL THEN 'preview' ELSE 'candidate' END WHERE status='working'")
            db.execute("UPDATE jobs SET status='expired' WHERE status='pending' AND (key LIKE 'scheduled-scan:%' OR kind IN ('digest','watch'))")
            return count

    def failed_retry(self, ident, version):
        with self.db() as db:
            db.execute("UPDATE jobs SET status='pending' WHERE story_id=? AND version=? AND status IN ('failed','interrupted')", (ident, version))
