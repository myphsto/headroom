"""OpenCode plugin for headroom learn.

Reads session data from ~/.local/share/opencode/opencode.db (SQLite).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from .._shared import classify_error, is_error_content, normalize_tool_name
from ..base import ConversationScanner, LearnPlugin
from ..models import (
    ErrorCategory,
    ProjectInfo,
    SessionData,
    SessionEvent,
    ToolCall,
)
from ..writer import ContextWriter, OpenCodeWriter

logger = logging.getLogger(__name__)

_OPENCODE_DATA_DIR = Path.home() / ".local" / "share" / "opencode"
_OPENCODE_DB_PATH = _OPENCODE_DATA_DIR / "opencode.db"


class OpenCodePlugin(LearnPlugin, ConversationScanner):
    """Reads OpenCode session data from SQLite database.

    OpenCode stores sessions in a SQLite database with tables:
    - session: id, project_id, directory, title, tokens, timestamps
    - message: id, session_id, data (JSON with role)
    - part: id, message_id, session_id, data (JSON with type/tool/state)
    - project: id, worktree, name
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or _OPENCODE_DB_PATH

    # --- LearnPlugin identity ---

    @property
    def name(self) -> str:
        return "opencode"

    @property
    def display_name(self) -> str:
        return "OpenCode"

    @property
    def description(self) -> str:
        return "OpenCode (~/.local/share/opencode/)"

    def detect(self) -> bool:
        return self.db_path.exists()

    def create_writer(self) -> ContextWriter:
        return OpenCodeWriter()

    # --- ConversationScanner interface ---

    def discover_projects(self) -> list[ProjectInfo]:
        """Discover projects from OpenCode session data."""
        if not self.db_path.exists():
            return []

        try:
            conn = sqlite3.connect(str(self.db_path))
            cur = conn.cursor()

            cur.execute(
                """
                SELECT DISTINCT s.directory, p.name
                FROM session s
                LEFT JOIN project p ON p.id = s.project_id
                ORDER BY s.time_updated DESC
                """
            )
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            logger.debug("Failed to query OpenCode database: %s", e)
            return []

        projects = []
        seen = set()
        for directory, project_name in rows:
            project_path = Path(directory) if directory else None
            if not project_path or not project_path.exists():
                continue
            if project_path in seen:
                continue
            seen.add(project_path)

            name = project_name or project_path.name
            agents_md = project_path / "AGENTS.md"

            projects.append(
                ProjectInfo(
                    name=name,
                    project_path=project_path,
                    data_path=_OPENCODE_DATA_DIR,
                    context_file=agents_md if agents_md.exists() else None,
                    memory_file=None,
                )
            )

        return projects

    def scan_project(self, project: ProjectInfo, max_workers: int = 1) -> list[SessionData]:
        """Scan all sessions for a project from the OpenCode database."""
        if not self.db_path.exists():
            return []

        try:
            conn = sqlite3.connect(str(self.db_path))
            cur = conn.cursor()

            cur.execute(
                """
                SELECT s.id, s.tokens_input, s.tokens_output
                FROM session s
                WHERE s.directory = ?
                ORDER BY s.time_updated DESC
                """,
                (str(project.project_path),),
            )
            sessions = cur.fetchall()
            conn.close()
        except Exception as e:
            logger.debug("Failed to query OpenCode sessions: %s", e)
            return []

        if max_workers <= 1 or len(sessions) <= 1:
            results = []
            for session_row in sessions:
                s = self._scan_session(session_row)
                if s and s.tool_calls:
                    results.append(s)
            return results

        from concurrent.futures import ThreadPoolExecutor, as_completed

        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(self._scan_session, row): row for row in sessions
            }
            for future in as_completed(futures):
                session = future.result()
                if session and session.tool_calls:
                    results.append(session)
        return results

    def _scan_session(self, session_row: tuple) -> SessionData | None:
        """Parse a single OpenCode session from the database."""
        session_id, tokens_input, tokens_output = session_row

        if not self.db_path.exists():
            return None

        try:
            conn = sqlite3.connect(str(self.db_path))
            cur = conn.cursor()

            cur.execute(
                """
                SELECT m.data, p.data
                FROM message m
                JOIN part p ON p.message_id = m.id
                WHERE m.session_id = ?
                ORDER BY m.time_created, p.time_created
                """,
                (session_id,),
            )
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            logger.debug("Failed to read session %s: %s", session_id, e)
            return None

        tool_calls: list[ToolCall] = []
        events: list[SessionEvent] = []
        msg_index = 0

        for msg_data, part_data in rows:
            try:
                msg = json.loads(msg_data) if isinstance(msg_data, str) else msg_data
                part = json.loads(part_data) if isinstance(part_data, str) else part_data
            except (json.JSONDecodeError, TypeError):
                continue

            msg_index += 1
            role = msg.get("role", "")

            if role == "user" and part.get("type") == "text":
                text = part.get("text", "")
                if isinstance(text, str) and text.strip():
                    events.append(
                        SessionEvent(
                            type="user_message",
                            msg_index=msg_index,
                            text=text[:500],
                        )
                    )

            if part.get("type") != "tool":
                continue

            tool_name = part.get("tool", "")
            state = part.get("state", {})
            if not isinstance(state, dict):
                continue

            call_id = part.get("callID", f"{session_id}_{msg_index}_{tool_name}")
            input_data = state.get("input", {})
            if not isinstance(input_data, dict):
                input_data = {}

            output = self._extract_output(state)
            is_err = self._is_tool_error(state)
            error_cat = (
                classify_error(output) if is_err else ErrorCategory.UNKNOWN
            )

            normalized_name = normalize_tool_name(tool_name)

            tc = ToolCall(
                name=normalized_name,
                tool_call_id=str(call_id),
                input_data=input_data,
                output=output,
                is_error=is_err,
                error_category=error_cat,
                msg_index=msg_index,
                output_bytes=len(output.encode("utf-8")) if output else 0,
            )
            tool_calls.append(tc)
            events.append(
                SessionEvent(
                    type="tool_call",
                    msg_index=msg_index,
                    tool_call=tc,
                )
            )

        events.sort(key=lambda e: e.msg_index)

        return SessionData(
            session_id=session_id,
            tool_calls=tool_calls,
            events=events,
            total_input_tokens=tokens_input or 0,
            total_output_tokens=tokens_output or 0,
        )

    def _extract_output(self, state: dict) -> str:
        """Extract output string from tool state."""
        output = state.get("output", "")
        if isinstance(output, str):
            return output
        if isinstance(output, dict):
            return json.dumps(output)
        return str(output) if output else ""

    def _is_tool_error(self, state: dict) -> bool:
        """Check if a tool call resulted in an error."""
        status = state.get("status", "")
        if status in ("error", "failed"):
            return True

        metadata = state.get("metadata", {})
        if isinstance(metadata, dict):
            exit_code = metadata.get("exit")
            if exit_code is not None and exit_code != 0:
                return True

        output = state.get("output", "")
        if isinstance(output, str):
            return is_error_content(output)

        return False


# Module-level instance for auto-discovery by the plugin registry
plugin = OpenCodePlugin()
