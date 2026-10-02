#!/usr/bin/env python3
"""Database layer for Repetitor: users, sessions, subscriptions, logs."""
import os, sqlite3, time, secrets, hashlib, hmac, json
from pathlib import Path
from contextlib import contextmanager

DB_PATH = os.environ.get('REPETITOR_DB', '/opt/repetitor/data.db')
SECRET_KEY = os.environ.get('REPETITOR_SECRET', 'change-me-in-production-please')

# Trial settings
TRIAL_DAYS = 14
TOKEN_TTL_HOURS = 24  # magic link validity

def init_db():
    """Create tables if not exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # 1. Create table (without username for backward compat — it'll be added via ALTER below)
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT,
        display_name TEXT,
        gender TEXT,                            -- 'f' | 'm' | null (unspecified)
        telegram_id INTEGER,
        telegram_username TEXT,
        role TEXT DEFAULT 'user',  -- 'user' | 'admin'
        created_at INTEGER NOT NULL,
        trial_until INTEGER,        -- unix ts; null = no trial
        subscription_until INTEGER, -- paid subscription end
        last_login_at INTEGER,
        is_active INTEGER DEFAULT 1,
        child_grade INTEGER DEFAULT 4,
        notes TEXT,
        learning_style TEXT,                    -- 'visual' | 'auditory' | 'kinesthetic' | 'mixed' | null
        learning_style_note TEXT,               -- free text: что любит (примеры, игры, разбор по шагам...)
        profile_completed_at INTEGER            -- когда ребёнок (или родитель) заполнил профиль
    );

    CREATE TABLE IF NOT EXISTS learning_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject TEXT NOT NULL,                  -- 'русский язык' | 'математика' | ...
        topic TEXT,                             -- конкретная тема ('причастный оборот', 'дроби')
        last_seen_at INTEGER NOT NULL,
        first_seen_at INTEGER NOT NULL,
        message_count INTEGER DEFAULT 1,
        success_count INTEGER DEFAULT 0,         -- thumbs up
        struggle_count INTEGER DEFAULT 0,        -- thumbs down или явные признаки ошибок
        confidence_avg REAL,                     -- средняя оценка 1..3
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    CREATE INDEX IF NOT EXISTS idx_progress_user ON learning_progress(user_id);

    CREATE TABLE IF NOT EXISTS learning_insights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category TEXT NOT NULL,                 -- 'interests' | 'strengths' | 'weaknesses' | 'style' | 'overall'
        summary TEXT NOT NULL,                  -- текст инсайта
        details TEXT,                           -- JSON: [{item, evidence}, ...]
        messages_analyzed INTEGER,              -- сколько последних сообщений учтено
        generated_at INTEGER NOT NULL,
        model_version TEXT,                     -- какая модель сгенерила
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    CREATE INDEX IF NOT EXISTS idx_insights_user ON learning_insights(user_id, generated_at);

    CREATE TABLE IF NOT EXISTS topic_difficulty (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        subject TEXT NOT NULL,
        topic TEXT NOT NULL,
        attempts INTEGER DEFAULT 1,
        failures INTEGER DEFAULT 0,             -- thumbs down или «не понял»
        last_attempt_at INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    CREATE INDEX IF NOT EXISTS idx_difficulty_user ON topic_difficulty(user_id, failures DESC);

    CREATE TABLE IF NOT EXISTS auth_tokens (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL,
        purpose TEXT,  -- 'magic_link' | 'session' | 'api'
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        consumed_at INTEGER,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS chat_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        session_id TEXT,           -- groups messages into a single chat session
        role TEXT,                  -- 'user' | 'assistant'
        content TEXT NOT NULL,
        grade INTEGER,
        subject TEXT,
        tokens_used INTEGER,
        latency_ms INTEGER,
        rating INTEGER,             -- 1 = thumbs down, 2 = neutral, 3 = thumbs up
        rated_at INTEGER,
        created_at INTEGER NOT NULL,
        kb_used INTEGER,
        meta TEXT,                    -- json: extra data (e.g. endpoint, ip)
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS subscription_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        event_type TEXT,             -- 'trial_started' | 'subscription_extended' | 'subscription_cancelled' | 'admin_extended'
        days INTEGER,
        from_until INTEGER,
        to_until INTEGER,
        amount_rub REAL,
        admin_id INTEGER,
        note TEXT,
        created_at INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );

    CREATE INDEX IF NOT EXISTS idx_logs_user_time ON chat_logs(user_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_logs_session ON chat_logs(session_id);
    CREATE INDEX IF NOT EXISTS idx_auth_user ON auth_tokens(user_id);
    CREATE INDEX IF NOT EXISTS idx_events_user ON subscription_events(user_id);
    ''')

    # 2. Migrations for existing tables (idempotent) — ADD COLUMN must happen after table exists
    for col, decl in [
        ('username', 'TEXT'),
        ('gender', 'TEXT'),
        ('learning_style', 'TEXT'),
        ('learning_style_note', 'TEXT'),
        ('profile_completed_at', 'INTEGER'),
    ]:
        try:
            c.execute(f'ALTER TABLE users ADD COLUMN {col} {decl}')
        except Exception:
            pass  # column already exists
    # Backfill username from email for legacy rows
    rows = c.execute("SELECT id, email, username FROM users WHERE username IS NULL OR username = ''").fetchall()
    for r in rows:
        eid = r['id']
        em = (r['email'] or '').strip()
        # If email looks like synthetic 'xxx@repetitor.local' → derive username
        if em.endswith('@repetitor.local'):
            uname = em[: -len('@repetitor.local')]
        else:
            uname = em.split('@')[0] or f'user{eid}'
        # Ensure unique: append numeric suffix if collision
        base = uname
        i = 1
        while c.execute('SELECT 1 FROM users WHERE username = ? AND id != ?', (uname, eid)).fetchone():
            i += 1
            uname = f'{base}{i}'
        c.execute('UPDATE users SET username = ? WHERE id = ?', (uname, eid))

    # 3. Indexes that depend on new columns go LAST
    c.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')

    conn.commit()
    conn.close()


# ============ Gender-aware Russian endings ============

def _gender_ending(gender: str | None, age_word: str = 'ребёнок') -> tuple[str, str]:
    """Return (subject_word, pronoun_word) gendered for Russian.
    Examples:
      ('f', 10) -> ('девочка', 'она')
      ('m', 10) -> ('мальчик', 'он')
      (None, 10) -> ('ребёнок', 'ты') — neutral
    """
    if gender == 'f':
        if age_word:
            pass
        return ('девочка', 'она')
    if gender == 'm':
        return ('мальчик', 'он')
    return ('ребёнок', 'ты')


def _verb_conjugate(gender: str | None, masc: str, fem: str) -> str:
    """Return proper past-tense verb form by gender.
    masc = 'узнал' / 'решил' / 'понял' / etc.
    fem  = 'узнала' / 'решила' / 'поняла' / etc.
    """
    if gender == 'f':
        return fem
    if gender == 'm':
        return masc
    return masc  # default to masc for neutral


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ============ Auth tokens (JWT-like, but with own secret) ============

def _b64url(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def _b64url_decode(s: str) -> bytes:
    import base64
    pad = '=' * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)

def make_token(payload: dict, ttl_seconds: int) -> str:
    """Make a signed token: base64(payload).base64(hmac). HMAC over payload with SECRET_KEY."""
    payload_b64 = _b64url(json.dumps(payload, separators=(',', ':')).encode())
    sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).digest()
    sig_b64 = _b64url(sig)
    return f'{payload_b64}.{sig_b64}'

def verify_token(token: str) -> dict | None:
    """Verify and decode token. Returns payload or None."""
    try:
        parts = token.split('.')
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts
        expected_sig = hmac.new(SECRET_KEY.encode(), payload_b64.encode(), hashlib.sha256).digest()
        actual_sig = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
        # Check expiry
        if 'exp' in payload and payload['exp'] < time.time():
            return None
        return payload
    except Exception:
        return None


# ============ User management ============

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100_000)
    return _b64url(salt) + '$' + _b64url(h)

def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, hash_b64 = stored.split('$', 1)
        salt = _b64url_decode(salt_b64)
        expected = _b64url_decode(hash_b64)
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100_000)
        return hmac.compare_digest(expected, actual)
    except Exception:
        return False


def _normalize_login(login: str) -> str:
    """Normalize a login: lowercase, strip whitespace. Both username and email formats allowed."""
    if not login:
        return ''
    return login.strip().lower()


def _validate_username(username: str) -> str | None:
    """Return None if OK, else error string. Allowed: 3-32 chars, letters/digits/_/.-"""
    import re as _re
    u = username.strip()
    if len(u) < 3:
        return 'username_too_short'
    if len(u) > 32:
        return 'username_too_long'
    if not _re.match(r'^[A-Za-z0-9_.\-а-яёА-ЯЁ]+$', u):
        return 'username_invalid_chars'
    return None


def create_user(email: str = '', username: str = '', password: str | None = None,
                display_name: str | None = None,
                gender: str = '',
                learning_style: str = '',
                learning_style_note: str = '',
                role: str = 'user', trial_days: int = TRIAL_DAYS) -> dict:
    """Create new user with trial. Returns user dict or raises ValueError.

    Two ways to create:
      - Provide email (legacy / external)
      - Provide username (new) — synthetic email will be generated
    Either email or username is required.
    """
    email_in = (email or '').strip().lower()
    username_in = (username or '').strip()

    if username_in and not email_in:
        # Synthetic email from username
        err = _validate_username(username_in)
        if err:
            raise ValueError(err)
        email_in = f'{username_in.lower()}@repetitor.local'
    elif email_in and not username_in:
        if '@' not in email_in:
            raise ValueError('invalid_email')
        # Derive username from local part of email
        uname = email_in.split('@')[0]
        # Validate it looks like a valid username
        err = _validate_username(uname)
        if err:
            # Auto-clean: replace dots with underscores
            import re as _re
            uname = _re.sub(r'[^A-Za-z0-9_а-яёА-ЯЁ]', '_', uname)
            err = _validate_username(uname)
            if err:
                raise ValueError(err)
        username_in = uname
    elif not email_in and not username_in:
        raise ValueError('login_required')

    with get_conn() as c:
        # Check username FIRST (more specific error code for the new field)
        if username_in:
            ex = c.execute('SELECT id FROM users WHERE username = ?', (username_in.lower(),)).fetchone()
            if ex:
                raise ValueError('username_exists')
        # Then check email
        existing = c.execute('SELECT id FROM users WHERE email = ?', (email_in,)).fetchone()
        if existing:
            raise ValueError('email_exists')

        now = int(time.time())
        trial_until = now + trial_days * 86400 if trial_days else None
        pwd_hash = hash_password(password) if password else None

        # Normalize gender
        g = (gender or '').strip().lower()
        if g in ('f', 'female', 'ж', 'женский', 'девочка', 'девушка'):
            g = 'f'
        elif g in ('m', 'male', 'м', 'мужской', 'мальчик'):
            g = 'm'
        else:
            g = None

        ls = (learning_style or '').strip().lower()
        if ls not in ('visual', 'auditory', 'kinesthetic', 'mixed', 'reading'):
            ls = None

        cur = c.execute('''
            INSERT INTO users (email, username, password_hash, display_name, gender, role,
                               learning_style, learning_style_note, profile_completed_at,
                               created_at, trial_until, child_grade)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (email_in, username_in.lower() if username_in else None, pwd_hash,
              display_name or (username_in or email_in.split('@')[0]), g, role,
              ls, learning_style_note or None,
              int(time.time()) if (g or ls or learning_style_note) else None,
              now, trial_until, 4))
        user_id = cur.lastrowid
        c.execute('''
            INSERT INTO subscription_events (user_id, event_type, days, to_until, created_at)
            VALUES (?, 'trial_started', ?, ?, ?)
        ''', (user_id, trial_days, trial_until, now))
        row = c.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_username(username: str) -> dict | None:
    with get_conn() as c:
        row = c.execute('SELECT * FROM users WHERE username = ?', (username.lower(),)).fetchone()
        return dict(row) if row else None


def find_user_by_login(login: str) -> dict | None:
    """Look up user by either username or email. Returns user dict or None."""
    l = _normalize_login(login)
    if not l:
        return None
    with get_conn() as c:
        # Try username first (cheap, indexed)
        row = c.execute('SELECT * FROM users WHERE username = ?', (l,)).fetchone()
        if row:
            return dict(row)
        # Try email
        row = c.execute('SELECT * FROM users WHERE email = ?', (l,)).fetchone()
        if row:
            return dict(row)
        # If '@repetitor.local' style — try synthetic
        if '@' not in l:
            row = c.execute('SELECT * FROM users WHERE email = ?', (f'{l}@repetitor.local',)).fetchone()
            if row:
                return dict(row)
        return None


def get_user(user_id: int) -> dict | None:
    with get_conn() as c:
        row = c.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        return dict(row) if row else None

def get_user_by_email(email: str) -> dict | None:
    with get_conn() as c:
        row = c.execute('SELECT * FROM users WHERE email = ?', (email.lower(),)).fetchone()
        return dict(row) if row else None


def user_has_access(user: dict) -> tuple[bool, str]:
    """Returns (has_access, reason)."""
    if user.get('role') == 'admin':
        return True, 'admin'
    now = int(time.time())
    if user.get('subscription_until') and user['subscription_until'] > now:
        return True, 'subscription'
    if user.get('trial_until') and user['trial_until'] > now:
        return True, 'trial'
    if not user.get('is_active'):
        return False, 'deactivated'
    return False, 'expired'


def extend_subscription(user_id: int, days: int, admin_id: int | None = None,
                        note: str = '', amount_rub: float = 0.0):
    """Extend subscription from current end date (or now) by N days."""
    with get_conn() as c:
        u = c.execute('SELECT subscription_until, trial_until FROM users WHERE id = ?', (user_id,)).fetchone()
        if not u:
            return None
        now = int(time.time())
        current_end = u['subscription_until'] or u['trial_until'] or now
        # If currently within paid sub, extend from current end
        # If trial expired, restart from now
        base = max(current_end, now)
        new_until = base + days * 86400
        c.execute('UPDATE users SET subscription_until = ?, is_active = 1 WHERE id = ?',
                  (new_until, user_id))
        c.execute('''
            INSERT INTO subscription_events (user_id, event_type, days, from_until, to_until, amount_rub, admin_id, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, 'subscription_extended' if admin_id else 'admin_extended',
              days, current_end, new_until, amount_rub, admin_id, note, now))
        return new_until


def cancel_subscription(user_id: int, admin_id: int, note: str = ''):
    with get_conn() as c:
        u = c.execute('SELECT subscription_until FROM users WHERE id = ?', (user_id,)).fetchone()
        if not u:
            return
        now = int(time.time())
        c.execute('UPDATE users SET subscription_until = NULL WHERE id = ?', (user_id,))
        c.execute('''
            INSERT INTO subscription_events (user_id, event_type, from_until, admin_id, note, created_at)
            VALUES (?, 'subscription_cancelled', ?, ?, ?, ?)
        ''', (user_id, u['subscription_until'], admin_id, note, now))


def deactivate_user(user_id: int, admin_id: int, note: str = ''):
    with get_conn() as c:
        c.execute('UPDATE users SET is_active = 0 WHERE id = ?', (user_id,))
        c.execute('''
            INSERT INTO subscription_events (user_id, event_type, admin_id, note, created_at)
            VALUES (?, 'deactivated', ?, ?, ?)
        ''', (user_id, admin_id, note, int(time.time())))


# ============ Auth token management ============

def create_magic_link(email: str) -> str:
    """Create one-time magic link token. Returns (token, user_id or None)."""
    with get_conn() as c:
        user = c.execute('SELECT id FROM users WHERE email = ?', (email.lower(),)).fetchone()
        if not user:
            return None, None
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        c.execute('''
            INSERT INTO auth_tokens (token, user_id, purpose, created_at, expires_at)
            VALUES (?, ?, 'magic_link', ?, ?)
        ''', (token, user['id'], now, now + TOKEN_TTL_HOURS * 3600))
        return token, user['id']


def create_session(user_id: int, ttl_days: int = 30) -> str:
    """Create long-lived session token for user."""
    with get_conn() as c:
        token = secrets.token_urlsafe(32)
        now = int(time.time())
        c.execute('''
            INSERT INTO auth_tokens (token, user_id, purpose, created_at, expires_at)
            VALUES (?, ?, 'session', ?, ?)
        ''', (token, user_id, now, now + ttl_days * 86400))
        c.execute('UPDATE users SET last_login_at = ? WHERE id = ?', (now, user_id))
        return token


def consume_token(token: str, purpose: str = 'magic_link') -> int | None:
    """Consume one-time token, return user_id or None."""
    with get_conn() as c:
        row = c.execute('SELECT user_id, expires_at, consumed_at FROM auth_tokens WHERE token = ? AND purpose = ?',
                        (token, purpose)).fetchone()
        if not row:
            return None
        if row['consumed_at']:
            return None
        if row['expires_at'] < int(time.time()):
            return None
        c.execute('UPDATE auth_tokens SET consumed_at = ? WHERE token = ?', (int(time.time()), token))
        return row['user_id']


def find_session(token: str) -> dict | None:
    """Find user by session token (if not expired)."""
    with get_conn() as c:
        row = c.execute('''
            SELECT u.*, t.expires_at as token_expires
            FROM auth_tokens t
            JOIN users u ON u.id = t.user_id
            WHERE t.token = ? AND t.purpose = 'session' AND t.consumed_at IS NULL
        ''', (token,)).fetchone()
        if not row:
            return None
        if row['token_expires'] < int(time.time()):
            return None
        return dict(row)


# ============ Chat logs ============

def log_chat(user_id: int, role: str, content: str, *,
             session_id: str = '', grade: int | None = None, subject: str | None = None,
             tokens_used: int | None = None, latency_ms: int | None = None,
             kb_used: bool | None = None, meta: dict | None = None) -> int:
    with get_conn() as c:
        cur = c.execute('''
            INSERT INTO chat_logs
                (user_id, session_id, role, content, grade, subject, tokens_used, latency_ms, kb_used, meta, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, session_id, role, content, grade, subject, tokens_used, latency_ms,
              1 if kb_used else 0 if kb_used is not None else None,
              json.dumps(meta, ensure_ascii=False) if meta else None,
              int(time.time() * 1000)))  # ms
        return cur.lastrowid


def rate_log(log_id: int, rating: int):
    """rating: 1=down, 2=neutral, 3=up. NULL clears."""
    with get_conn() as c:
        c.execute('UPDATE chat_logs SET rating = ?, rated_at = ? WHERE id = ?',
                  (rating, int(time.time() * 1000), log_id))


# ============ Profile, progress, insights ============

def update_user_profile(user_id: int, *, display_name: str | None = None,
                        gender: str | None = None,
                        learning_style: str | None = None,
                        learning_style_note: str | None = None,
                        child_grade: int | None = None,
                        mark_completed: bool = False) -> dict | None:
    """Update user profile fields. None means don't change.
    Returns updated user dict, or None if user not found."""
    updates = []
    params = []
    if display_name is not None:
        updates.append('display_name = ?')
        params.append(display_name)
    if gender is not None:
        # normalize
        g = gender.strip().lower()
        if g in ('f', 'female', 'ж', 'женский', 'девочка', 'девушка'):
            g = 'f'
        elif g in ('m', 'male', 'м', 'мужской', 'мальчик'):
            g = 'm'
        else:
            g = None
        updates.append('gender = ?')
        params.append(g)
    if learning_style is not None:
        ls = learning_style.strip().lower()
        if ls not in ('visual', 'auditory', 'kinesthetic', 'mixed', 'reading'):
            ls = None
        updates.append('learning_style = ?')
        params.append(ls)
    if learning_style_note is not None:
        updates.append('learning_style_note = ?')
        params.append(learning_style_note)
    if child_grade is not None:
        updates.append('child_grade = ?')
        params.append(max(1, min(11, child_grade)))
    if mark_completed:
        updates.append('profile_completed_at = ?')
        params.append(int(time.time()))

    if not updates:
        return get_user(user_id)

    params.append(user_id)
    with get_conn() as c:
        c.execute(f'UPDATE users SET {", ".join(updates)} WHERE id = ?', params)
        row = c.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        return dict(row) if row else None


def upsert_progress(user_id: int, subject: str, topic: str = '',
                    rating: int | None = None) -> None:
    """Increment counters for (user, subject, topic). rating 1..3 or None."""
    now = int(time.time())
    with get_conn() as c:
        row = c.execute('''
            SELECT id, message_count, success_count, struggle_count, confidence_avg
            FROM learning_progress
            WHERE user_id = ? AND subject = ? AND IFNULL(topic,'') = ?
        ''', (user_id, subject, topic or '')).fetchone()
        if row:
            new_count = row['message_count'] + 1
            new_success = row['success_count']
            new_struggle = row['struggle_count']
            new_conf_sum = (row['confidence_avg'] or 0) * row['message_count']
            if rating == 3:
                new_success += 1
            elif rating == 1:
                new_struggle += 1
            if rating is not None:
                new_conf_sum += rating
                new_conf_avg = new_conf_sum / new_count
            else:
                new_conf_avg = row['confidence_avg']
            c.execute('''
                UPDATE learning_progress
                SET message_count = ?, success_count = ?, struggle_count = ?,
                    confidence_avg = ?, last_seen_at = ?
                WHERE id = ?
            ''', (new_count, new_success, new_struggle, new_conf_avg, now, row['id']))
        else:
            conf_avg = float(rating) if rating is not None else None
            success = 1 if rating == 3 else 0
            struggle = 1 if rating == 1 else 0
            c.execute('''
                INSERT INTO learning_progress
                    (user_id, subject, topic, last_seen_at, first_seen_at,
                     message_count, success_count, struggle_count, confidence_avg)
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
            ''', (user_id, subject, topic or None, now, now, success, struggle, conf_avg))


def list_progress(user_id: int, limit: int = 50) -> list[dict]:
    with get_conn() as c:
        rows = c.execute('''
            SELECT subject, topic, message_count, success_count, struggle_count,
                   confidence_avg, last_seen_at, first_seen_at
            FROM learning_progress
            WHERE user_id = ?
            ORDER BY last_seen_at DESC
            LIMIT ?
        ''', (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


def save_insight(user_id: int, category: str, summary: str, details: list | None = None,
                 messages_analyzed: int | None = None, model_version: str | None = None) -> int:
    with get_conn() as c:
        cur = c.execute('''
            INSERT INTO learning_insights
                (user_id, category, summary, details, messages_analyzed, generated_at, model_version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, category, summary,
              json.dumps(details, ensure_ascii=False) if details else None,
              messages_analyzed, int(time.time()), model_version))
        return cur.lastrowid


def list_insights(user_id: int, category: str | None = None, limit: int = 50) -> list[dict]:
    with get_conn() as c:
        if category:
            rows = c.execute('''
                SELECT * FROM learning_insights
                WHERE user_id = ? AND category = ?
                ORDER BY generated_at DESC LIMIT ?
            ''', (user_id, category, limit)).fetchall()
        else:
            rows = c.execute('''
                SELECT * FROM learning_insights
                WHERE user_id = ?
                ORDER BY generated_at DESC LIMIT ?
            ''', (user_id, limit)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get('details'):
                try:
                    d['details'] = json.loads(d['details'])
                except Exception:
                    pass
            out.append(d)
        return out


def get_latest_insight(user_id: int, category: str) -> dict | None:
    with get_conn() as c:
        row = c.execute('''
            SELECT * FROM learning_insights
            WHERE user_id = ? AND category = ?
            ORDER BY generated_at DESC LIMIT 1
        ''', (user_id, category)).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get('details'):
            try:
                d['details'] = json.loads(d['details'])
            except Exception:
                pass
        return d


def count_messages_since_last_insight(user_id: int) -> int:
    """Return how many user messages since the last insight of any category was generated."""
    with get_conn() as c:
        last = c.execute('''
            SELECT MAX(generated_at) FROM learning_insights WHERE user_id = ?
        ''', (user_id,)).fetchone()[0]
        if not last:
            last = 0
        n = c.execute('''
            SELECT COUNT(*) FROM chat_logs
            WHERE user_id = ? AND role = 'user' AND created_at >= ?
        ''', (user_id, int(last) * 1000)).fetchone()[0]
        return n


def upsert_topic_difficulty(user_id: int, subject: str, topic: str, *, struggled: bool) -> None:
    """Track per-topic attempts and failures (thumbs down or explicit 'не понял')."""
    if not topic:
        return
    now = int(time.time())
    with get_conn() as c:
        row = c.execute('''
            SELECT id, attempts, failures FROM topic_difficulty
            WHERE user_id = ? AND subject = ? AND topic = ?
        ''', (user_id, subject, topic)).fetchone()
        if row:
            attempts = row['attempts'] + 1
            failures = row['failures'] + (1 if struggled else 0)
            c.execute('''
                UPDATE topic_difficulty SET attempts = ?, failures = ?, last_attempt_at = ?
                WHERE id = ?
            ''', (attempts, failures, now, row['id']))
        else:
            c.execute('''
                INSERT INTO topic_difficulty (user_id, subject, topic, attempts, failures, last_attempt_at)
                VALUES (?, ?, ?, 1, ?, ?)
            ''', (user_id, subject, topic, 1 if struggled else 0, now))


def list_top_difficult_topics(user_id: int, limit: int = 10) -> list[dict]:
    with get_conn() as c:
        rows = c.execute('''
            SELECT subject, topic, attempts, failures, last_attempt_at
            FROM topic_difficulty
            WHERE user_id = ?
            ORDER BY failures DESC, attempts DESC
            LIMIT ?
        ''', (user_id, limit)).fetchall()
        return [dict(r) for r in rows]


# ============ Admin queries ============

def list_users(limit: int = 100, offset: int = 0, search: str | None = None) -> list[dict]:
    with get_conn() as c:
        if search:
            like = f'%{search.lower()}%'
            rows = c.execute('''
                SELECT * FROM users
                WHERE LOWER(email) LIKE ?
                   OR LOWER(username) LIKE ?
                   OR LOWER(display_name) LIKE ?
                ORDER BY id DESC LIMIT ? OFFSET ?
            ''', (like, like, like, limit, offset)).fetchall()
        else:
            rows = c.execute('SELECT * FROM users ORDER BY id DESC LIMIT ? OFFSET ?',
                             (limit, offset)).fetchall()
        return [dict(r) for r in rows]


def count_users() -> int:
    with get_conn() as c:
        return c.execute('SELECT COUNT(*) FROM users').fetchone()[0]


def list_logs(user_id: int | None = None, limit: int = 100, rating_filter: int | None = None) -> list[dict]:
    with get_conn() as c:
        if user_id:
            rows = c.execute('''
                SELECT l.*, u.email as user_email
                FROM chat_logs l
                JOIN users u ON u.id = l.user_id
                WHERE l.user_id = ?
                ORDER BY l.id DESC LIMIT ?
            ''', (user_id, limit)).fetchall()
        else:
            rows = c.execute('''
                SELECT l.*, u.email as user_email
                FROM chat_logs l
                JOIN users u ON u.id = l.user_id
                ORDER BY l.id DESC LIMIT ?
            ''', (limit,)).fetchall()
        out = [dict(r) for r in rows]
        if rating_filter:
            out = [r for r in out if r.get('rating') == rating_filter]
        return out


def get_stats() -> dict:
    """Aggregate stats for admin dashboard."""
    with get_conn() as c:
        now = int(time.time())
        total_users = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        active_trials = c.execute('SELECT COUNT(*) FROM users WHERE trial_until > ? AND subscription_until IS NULL', (now,)).fetchone()[0]
        active_subs = c.execute('SELECT COUNT(*) FROM users WHERE subscription_until > ?', (now,)).fetchone()[0]
        total_logs = c.execute('SELECT COUNT(*) FROM chat_logs').fetchone()[0]
        total_user_msgs = c.execute("SELECT COUNT(*) FROM chat_logs WHERE role = 'user'").fetchone()[0]
        total_assistant_msgs = c.execute("SELECT COUNT(*) FROM chat_logs WHERE role = 'assistant'").fetchone()[0]
        rated_up = c.execute('SELECT COUNT(*) FROM chat_logs WHERE rating = 3').fetchone()[0]
        rated_down = c.execute('SELECT COUNT(*) FROM chat_logs WHERE rating = 1').fetchone()[0]
        rated_total = rated_up + rated_down
        # last 7 days
        seven_days_ago = now - 7 * 86400
        recent_users = c.execute('SELECT COUNT(*) FROM users WHERE created_at > ?', (seven_days_ago,)).fetchone()[0]
        recent_msgs = c.execute('SELECT COUNT(*) FROM chat_logs WHERE created_at > ?', (seven_days_ago * 1000,)).fetchone()[0]
        return {
            'total_users': total_users,
            'active_trials': active_trials,
            'active_subs': active_subs,
            'expired': total_users - active_trials - active_subs,
            'total_messages': total_logs,
            'user_messages': total_user_msgs,
            'assistant_messages': total_assistant_msgs,
            'rated_total': rated_total,
            'rated_up': rated_up,
            'rated_down': rated_down,
            'satisfaction_pct': round(100 * rated_up / rated_total) if rated_total else None,
            'recent_7d_users': recent_users,
            'recent_7d_messages': recent_msgs,
        }


# ============ Init ============
init_db()