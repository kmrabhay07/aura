"""Opt-in local text-only history. No screenshots, audio, settings or keys."""
import json
from pathlib import Path
import sqlite3
import time
import uuid


class HistoryStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, title TEXT, updated REAL, messages TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS deleted_sessions (id TEXT PRIMARY KEY)')

    def connect(self):
        db=sqlite3.connect(self.path, timeout=.3)
        db.execute("PRAGMA secure_delete=ON")
        return db

    def save(self, session_id, messages):
        if len(messages)%2 or any(m.get('role') != ('user' if i%2==0 else 'assistant') for i,m in enumerate(messages)):
            raise ValueError('Complete conversation pairs are required')
        safe = []
        for message in messages:
            if set(message) != {'role','content'} or message['role'] not in ('user','assistant') or not isinstance(message['content'],str):
                raise ValueError('Only plain text conversation turns may be saved')
            safe.append({'role':message['role'],'content':message['content'][:8000]})
        safe = safe[-24:]
        while safe and sum(len(m['content']) for m in safe)>24000:
            safe = safe[2:]
        if not safe:
            return
        title = next((m['content'][:70] for m in safe if m['role']=='user'), 'Conversation')
        with self.connect() as db:
            if db.execute('SELECT 1 FROM deleted_sessions WHERE id=?',(session_id,)).fetchone():
                return
            db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?,?,?)',
                       (session_id,title,time.time(),json.dumps(safe,ensure_ascii=False)))
            db.execute('DELETE FROM sessions WHERE id NOT IN (SELECT id FROM sessions ORDER BY updated DESC LIMIT 30)')

    def list_sessions(self):
        with self.connect() as db:
            return db.execute('SELECT id,title,updated FROM sessions ORDER BY updated DESC').fetchall()

    def load(self, session_id):
        with self.connect() as db:
            row = db.execute('SELECT messages FROM sessions WHERE id=?',(session_id,)).fetchone()
        messages = json.loads(row[0]) if row else []
        if len(messages)%2 or any(m.get('role') != ('user' if i%2==0 else 'assistant') or
                not isinstance(m.get('content'),str) for i,m in enumerate(messages)):
            raise ValueError('Saved conversation is invalid')
        return messages

    def delete(self, session_id):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO deleted_sessions VALUES (?)',(session_id,))
            db.execute('DELETE FROM sessions WHERE id=?',(session_id,))

    @staticmethod
    def new_id():
        return uuid.uuid4().hex
