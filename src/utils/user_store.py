from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from src.utils.security import hash_password, verify_password
from src.utils.storage import connect_metadata_db

_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{3,40}$")


@dataclass(frozen=True)
class UserAccount:
    user_id: str
    username: str
    role: str
    created_at: datetime
    updated_at: datetime


def normalize_username(username: str) -> str:
    return username.strip().lower()


def validate_username(username: str) -> None:
    if not _USERNAME_PATTERN.match(username):
        raise ValueError("Username must be 3-40 chars and use letters, numbers, dot, underscore, or hyphen.")


def _row_to_user(row) -> UserAccount:
    return UserAccount(
        user_id=row["user_id"],
        username=row["username"],
        role=row["role"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def get_user_by_username(username: str) -> UserAccount | None:
    normalized = normalize_username(username)
    with connect_metadata_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (normalized,)).fetchone()
    if row is None:
        return None
    return _row_to_user(row)


def _validate_reset_answer(answer: str) -> None:
    if len(answer.strip()) < 3:
        raise ValueError("Reset answer must be at least 3 characters.")


def create_user(
    username: str,
    password: str,
    *,
    reset_question: str,
    reset_answer: str,
    role: str = "user",
) -> UserAccount:
    normalized = normalize_username(username)
    validate_username(normalized)
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if not reset_question.strip():
        raise ValueError("Reset question is required.")
    _validate_reset_answer(reset_answer)
    now = datetime.now(UTC).isoformat()
    user_id = uuid.uuid4().hex
    password_hash = hash_password(password)
    answer_hash = hash_password(reset_answer.strip())
    with connect_metadata_db() as conn:
        existing = conn.execute("SELECT 1 FROM users WHERE username = ?", (normalized,)).fetchone()
        if existing:
            raise ValueError("Username already exists.")
        conn.execute(
            """
            INSERT INTO users (user_id, username, password_hash, reset_question, reset_answer_hash, role, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, normalized, password_hash, reset_question.strip(), answer_hash, role, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        raise ValueError("Unable to create user.")
    return _row_to_user(row)


def authenticate_user(username: str, password: str) -> UserAccount | None:
    normalized = normalize_username(username)
    with connect_metadata_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (normalized,)).fetchone()
    if row is None:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return _row_to_user(row)


def get_reset_question(username: str) -> str | None:
    normalized = normalize_username(username)
    with connect_metadata_db() as conn:
        row = conn.execute("SELECT reset_question FROM users WHERE username = ?", (normalized,)).fetchone()
    if row is None:
        return None
    question = row["reset_question"]
    return str(question).strip() if question else None


def update_reset_credentials(username: str, *, reset_question: str, reset_answer: str) -> UserAccount:
    normalized = normalize_username(username)
    if not reset_question.strip():
        raise ValueError("Reset question is required.")
    _validate_reset_answer(reset_answer)
    answer_hash = hash_password(reset_answer.strip())
    now = datetime.now(UTC).isoformat()
    with connect_metadata_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (normalized,)).fetchone()
        if row is None:
            raise ValueError("User not found.")
        conn.execute(
            """
            UPDATE users
            SET reset_question = ?, reset_answer_hash = ?, updated_at = ?
            WHERE username = ?
            """,
            (reset_question.strip(), answer_hash, now, normalized),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM users WHERE username = ?", (normalized,)).fetchone()
    if updated is None:
        raise ValueError("User not found.")
    return _row_to_user(updated)


def change_password(username: str, *, current_password: str, new_password: str) -> UserAccount:
    normalized = normalize_username(username)
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    now = datetime.now(UTC).isoformat()
    with connect_metadata_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (normalized,)).fetchone()
        if row is None:
            raise ValueError("User not found.")
        if not verify_password(current_password, row["password_hash"]):
            raise ValueError("Current password is incorrect.")
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE username = ?",
            (hash_password(new_password), now, normalized),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM users WHERE username = ?", (normalized,)).fetchone()
    if updated is None:
        raise ValueError("User not found.")
    return _row_to_user(updated)


def reset_password_with_answer(username: str, *, reset_answer: str, new_password: str) -> UserAccount:
    normalized = normalize_username(username)
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    now = datetime.now(UTC).isoformat()
    with connect_metadata_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (normalized,),
        ).fetchone()
        if row is None:
            raise ValueError("User not found.")
        stored_answer = row["reset_answer_hash"]
        if not stored_answer:
            raise ValueError("Reset question is not configured.")
        if not verify_password(reset_answer.strip(), stored_answer):
            raise ValueError("Reset answer is incorrect.")
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE username = ?",
            (hash_password(new_password), now, normalized),
        )
        conn.commit()
        updated = conn.execute("SELECT * FROM users WHERE username = ?", (normalized,)).fetchone()
    if updated is None:
        raise ValueError("User not found.")
    return _row_to_user(updated)
