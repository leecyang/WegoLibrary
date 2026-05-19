import os
import socket
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests


REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
PYTHON_EXE = REPO_ROOT / ".venv" / "Scripts" / "python.exe"


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_server(tmp_path, ttl_seconds=120):
    db_path = tmp_path / "auth_test.db"
    port = _find_free_port()
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
    env["SECRET_KEY"] = "test-secret-key"
    env["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
    env["AUTH_SESSION_TTL_SECONDS"] = str(ttl_seconds)

    proc = subprocess.Popen(
        [
            str(PYTHON_EXE),
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(BACKEND_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    base_url = f"http://127.0.0.1:{port}"
    last_error = None
    for _ in range(60):
        try:
            response = requests.get(f"{base_url}/openapi.json", timeout=1)
            if response.status_code == 200:
                return proc, base_url, db_path
        except Exception as exc:
            last_error = exc
        time.sleep(0.5)

    output = ""
    if proc.stdout:
        try:
            output = proc.stdout.read()
        except Exception:
            output = ""
    proc.terminate()
    proc.wait(timeout=10)
    raise RuntimeError(f"server did not start: {last_error}\n{output}")


def _stop_server(proc: subprocess.Popen):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def _auth_session_table_name(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    for (table_name,) in rows:
        columns = {
            row[1]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if {"token_hash", "expires_at", "revoked_at"}.issubset(columns):
            return table_name
    raise AssertionError("auth session table not found")


def _get_auth_session_row(db_path: Path):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        table_name = _auth_session_table_name(conn)
        row = conn.execute(f"SELECT * FROM {table_name} ORDER BY id ASC LIMIT 1").fetchone()
        assert row is not None
        return dict(row), table_name


def _set_auth_session_expiry(db_path: Path, expires_at: datetime):
    with sqlite3.connect(db_path) as conn:
        table_name = _auth_session_table_name(conn)
        conn.execute(
            f"UPDATE {table_name} SET expires_at = ? WHERE id = (SELECT id FROM {table_name} ORDER BY id ASC LIMIT 1)",
            (expires_at.strftime("%Y-%m-%d %H:%M:%S.%f"),),
        )
        conn.commit()


def _parse_db_datetime(value):
    return datetime.fromisoformat(value) if value else None


def _register_and_login(session: requests.Session, base_url: str):
    register_res = session.post(
        f"{base_url}/api/auth/register",
        json={"username": "alice", "password": "secret123"},
        timeout=10,
    )
    assert register_res.status_code == 200, register_res.text

    login_res = session.post(
        f"{base_url}/api/auth/login",
        data={"username": "alice", "password": "secret123"},
        timeout=10,
    )
    assert login_res.status_code == 200, login_res.text
    return login_res


def test_login_sets_persistent_cookie_and_cookie_only_auth_works(tmp_path):
    proc, base_url, db_path = _start_server(tmp_path, ttl_seconds=120)
    try:
        session = requests.Session()
        login_res = _register_and_login(session, base_url)
        set_cookie = login_res.headers["set-cookie"].lower()

        assert "wegolibrary_session=" in set_cookie
        assert "httponly" in set_cookie
        assert "samesite=lax" in set_cookie
        assert "max-age=120" in set_cookie

        me_res = session.get(f"{base_url}/api/auth/me", timeout=10)
        assert me_res.status_code == 200, me_res.text
        assert me_res.json()["username"] == "alice"

        auth_session, _ = _get_auth_session_row(db_path)
        assert auth_session["revoked_at"] is None
    finally:
        _stop_server(proc)


def test_cookie_session_slides_forward_and_logout_revokes_it(tmp_path):
    proc, base_url, db_path = _start_server(tmp_path, ttl_seconds=120)
    try:
        session = requests.Session()
        login_res = _register_and_login(session, base_url)
        bearer_token = login_res.json()["access_token"]

        _set_auth_session_expiry(db_path, datetime.now() + timedelta(seconds=5))

        me_res = session.get(f"{base_url}/api/auth/me", timeout=10)
        assert me_res.status_code == 200, me_res.text

        auth_session, _ = _get_auth_session_row(db_path)
        assert _parse_db_datetime(auth_session["expires_at"]) > datetime.now() + timedelta(seconds=90)
        assert _parse_db_datetime(auth_session["last_used_at"]) >= _parse_db_datetime(auth_session["created_at"])
        assert auth_session["revoked_at"] is None

        logout_res = session.post(f"{base_url}/api/auth/logout", timeout=10)
        assert logout_res.status_code == 200, logout_res.text

        me_after_logout = session.get(f"{base_url}/api/auth/me", timeout=10)
        assert me_after_logout.status_code == 401, me_after_logout.text

        bearer_res = requests.get(
            f"{base_url}/api/auth/me",
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=10,
        )
        assert bearer_res.status_code == 200, bearer_res.text

        auth_session, _ = _get_auth_session_row(db_path)
        assert auth_session["revoked_at"] is not None
    finally:
        _stop_server(proc)


def test_expired_cookie_session_returns_unauthorized(tmp_path):
    proc, base_url, db_path = _start_server(tmp_path, ttl_seconds=120)
    try:
        session = requests.Session()
        _register_and_login(session, base_url)

        _set_auth_session_expiry(db_path, datetime.now() - timedelta(seconds=1))

        me_res = session.get(f"{base_url}/api/auth/me", timeout=10)
        assert me_res.status_code == 401, me_res.text
    finally:
        _stop_server(proc)
