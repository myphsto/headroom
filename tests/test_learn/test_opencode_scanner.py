"""Unit tests for OpenCodePlugin — OpenCode session scanning from SQLite.

Tests use a synthetic SQLite database in a temp directory, no real OpenCode data needed.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from headroom.learn.models import ProjectInfo, Recommendation, RecommendationTarget
from headroom.learn.plugins.opencode import OpenCodePlugin
from headroom.learn.writer import OpenCodeWriter


def _create_test_db(
    db_path: Path,
    project_dir: Path,
    session_id: str = "ses_test123",
    tool_parts: list[dict] | None = None,
    user_texts: list[str] | None = None,
    tokens_input: int = 1000,
    tokens_output: int = 200,
) -> None:
    """Create a minimal OpenCode-like SQLite database for testing."""
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS project (
            id TEXT PRIMARY KEY,
            worktree TEXT NOT NULL,
            name TEXT,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS session (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            directory TEXT NOT NULL,
            title TEXT NOT NULL,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            tokens_input INTEGER DEFAULT 0,
            tokens_output INTEGER DEFAULT 0
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS message (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            data TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS part (
            id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            time_created INTEGER NOT NULL,
            time_updated INTEGER NOT NULL,
            data TEXT NOT NULL
        )
        """
    )

    cur.execute(
        "INSERT INTO project VALUES (?, ?, ?, 1000, 2000)",
        ("proj_1", str(project_dir), "test-project"),
    )
    cur.execute(
        "INSERT INTO session VALUES (?, ?, ?, 'Test Session', 1000, 2000, ?, ?)",
        (session_id, "proj_1", str(project_dir), tokens_input, tokens_output),
    )

    msg_idx = 0
    if user_texts:
        for text in user_texts:
            msg_idx += 1
            msg_id = f"msg_{msg_idx}"
            msg_data = json.dumps({"role": "user", "time": 1000})
            cur.execute(
                "INSERT INTO message VALUES (?, ?, 1000, 2000, ?)",
                (msg_id, session_id, msg_data),
            )
            part_data = json.dumps({"type": "text", "text": text})
            cur.execute(
                "INSERT INTO part VALUES (?, ?, ?, 1000, 2000, ?)",
                (f"part_{msg_idx}_text", msg_id, session_id, part_data),
            )

    if tool_parts:
        for i, tp in enumerate(tool_parts):
            msg_idx += 1
            msg_id = f"msg_{msg_idx}"
            msg_data = json.dumps({"role": "assistant", "time": 1000})
            cur.execute(
                "INSERT INTO message VALUES (?, ?, 1000, 2000, ?)",
                (msg_id, session_id, msg_data),
            )
            part_data = json.dumps(tp)
            cur.execute(
                "INSERT INTO part VALUES (?, ?, ?, 1000, 2000, ?)",
                (f"part_{msg_idx}_tool", msg_id, session_id, part_data),
            )

    conn.commit()
    conn.close()


class TestPluginIdentity:
    def test_name(self):
        plugin = OpenCodePlugin()
        assert plugin.name == "opencode"

    def test_display_name(self):
        plugin = OpenCodePlugin()
        assert plugin.display_name == "OpenCode"

    def test_description(self):
        plugin = OpenCodePlugin()
        assert "OpenCode" in plugin.description

    def test_create_writer(self):
        plugin = OpenCodePlugin()
        writer = plugin.create_writer()
        assert isinstance(writer, OpenCodeWriter)


class TestDetect:
    def test_detects_existing_db(self, tmp_path):
        db_path = tmp_path / "opencode.db"
        db_path.touch()
        plugin = OpenCodePlugin(db_path=db_path)
        assert plugin.detect() is True

    def test_no_detect_missing_db(self, tmp_path):
        db_path = tmp_path / "opencode.db"
        plugin = OpenCodePlugin(db_path=db_path)
        assert plugin.detect() is False


class TestProjectDiscovery:
    def test_no_db(self, tmp_path):
        plugin = OpenCodePlugin(db_path=tmp_path / "missing.db")
        assert plugin.discover_projects() == []

    def test_empty_db(self, tmp_path):
        db_path = tmp_path / "opencode.db"
        conn = sqlite3.connect(str(db_path))
        conn.close()
        plugin = OpenCodePlugin(db_path=db_path)
        assert plugin.discover_projects() == []

    def test_discovers_project(self, tmp_path):
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        db_path = tmp_path / "opencode.db"
        _create_test_db(db_path, project_dir)

        plugin = OpenCodePlugin(db_path=db_path)
        projects = plugin.discover_projects()

        assert len(projects) == 1
        assert projects[0].project_path == project_dir
        assert projects[0].name == "test-project"


class TestSessionScanning:
    def test_basic_tool_call(self, tmp_path):
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        db_path = tmp_path / "opencode.db"
        _create_test_db(
            db_path,
            project_dir,
            tool_parts=[
                {
                    "type": "tool",
                    "tool": "bash",
                    "callID": "call_1",
                    "state": {
                        "status": "completed",
                        "input": {"command": "ls -la"},
                        "output": "total 0\ndrwxr-xr-x",
                        "metadata": {"exit": 0},
                    },
                }
            ],
        )

        plugin = OpenCodePlugin(db_path=db_path)
        projects = plugin.discover_projects()
        sessions = plugin.scan_project(projects[0])

        assert len(sessions) == 1
        assert len(sessions[0].tool_calls) == 1
        tc = sessions[0].tool_calls[0]
        assert tc.name == "Bash"
        assert tc.tool_call_id == "call_1"
        assert not tc.is_error
        assert "ls -la" in json.dumps(tc.input_data)

    def test_tool_error_detection_status(self, tmp_path):
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        db_path = tmp_path / "opencode.db"
        _create_test_db(
            db_path,
            project_dir,
            tool_parts=[
                {
                    "type": "tool",
                    "tool": "bash",
                    "callID": "call_err",
                    "state": {
                        "status": "error",
                        "input": {"command": "false"},
                        "output": "Error: command failed",
                    },
                }
            ],
        )

        plugin = OpenCodePlugin(db_path=db_path)
        projects = plugin.discover_projects()
        sessions = plugin.scan_project(projects[0])

        tc = sessions[0].tool_calls[0]
        assert tc.is_error

    def test_tool_error_detection_exit_code(self, tmp_path):
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        db_path = tmp_path / "opencode.db"
        _create_test_db(
            db_path,
            project_dir,
            tool_parts=[
                {
                    "type": "tool",
                    "tool": "bash",
                    "callID": "call_exit",
                    "state": {
                        "status": "completed",
                        "input": {"command": "exit 1"},
                        "output": "Error: something went wrong",
                        "metadata": {"exit": 1},
                    },
                }
            ],
        )

        plugin = OpenCodePlugin(db_path=db_path)
        projects = plugin.discover_projects()
        sessions = plugin.scan_project(projects[0])

        tc = sessions[0].tool_calls[0]
        assert tc.is_error

    def test_multiple_tool_calls(self, tmp_path):
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        db_path = tmp_path / "opencode.db"
        _create_test_db(
            db_path,
            project_dir,
            tool_parts=[
                {
                    "type": "tool",
                    "tool": "glob",
                    "callID": "call_glob",
                    "state": {
                        "status": "completed",
                        "input": {"pattern": "*.py"},
                        "output": "main.py\ntest.py",
                    },
                },
                {
                    "type": "tool",
                    "tool": "read",
                    "callID": "call_read",
                    "state": {
                        "status": "completed",
                        "input": {"file_path": "main.py"},
                        "output": "print('hello')",
                    },
                },
            ],
        )

        plugin = OpenCodePlugin(db_path=db_path)
        projects = plugin.discover_projects()
        sessions = plugin.scan_project(projects[0])

        assert len(sessions[0].tool_calls) == 2
        assert sessions[0].tool_calls[0].name == "Glob"
        assert sessions[0].tool_calls[1].name == "Read"

    def test_user_messages_extracted(self, tmp_path):
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        db_path = tmp_path / "opencode.db"
        _create_test_db(
            db_path,
            project_dir,
            user_texts=["list the files", "now run the tests"],
            tool_parts=[
                {
                    "type": "tool",
                    "tool": "bash",
                    "callID": "call_1",
                    "state": {
                        "status": "completed",
                        "input": {"command": "ls"},
                        "output": "main.py",
                    },
                }
            ],
        )

        plugin = OpenCodePlugin(db_path=db_path)
        projects = plugin.discover_projects()
        sessions = plugin.scan_project(projects[0])

        user_events = [e for e in sessions[0].events if e.type == "user_message"]
        assert len(user_events) == 2
        assert "list the files" in user_events[0].text
        assert "run the tests" in user_events[1].text

    def test_no_tool_calls_filtered(self, tmp_path):
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        db_path = tmp_path / "opencode.db"
        _create_test_db(
            db_path,
            project_dir,
            user_texts=["hello"],
            tool_parts=[],
        )

        plugin = OpenCodePlugin(db_path=db_path)
        projects = plugin.discover_projects()
        sessions = plugin.scan_project(projects[0])

        assert len(sessions) == 0

    def test_tokens_captured(self, tmp_path):
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()
        db_path = tmp_path / "opencode.db"
        _create_test_db(
            db_path,
            project_dir,
            tokens_input=5000,
            tokens_output=300,
            tool_parts=[
                {
                    "type": "tool",
                    "tool": "bash",
                    "callID": "call_1",
                    "state": {
                        "status": "completed",
                        "input": {"command": "echo hi"},
                        "output": "hi",
                    },
                }
            ],
        )

        plugin = OpenCodePlugin(db_path=db_path)
        projects = plugin.discover_projects()
        sessions = plugin.scan_project(projects[0])

        assert sessions[0].total_input_tokens == 5000
        assert sessions[0].total_output_tokens == 300


class TestOpenCodeWriter:
    def test_writes_to_agents_md(self, tmp_path):
        proj = ProjectInfo(
            name="test", project_path=tmp_path, data_path=tmp_path
        )
        recs = [
            Recommendation(
                target=RecommendationTarget.CONTEXT_FILE,
                section="Commands",
                content="- Use `pytest`",
                confidence=0.9,
                evidence_count=5,
            ),
        ]

        writer = OpenCodeWriter()
        result = writer.write(recs, proj, dry_run=False)

        assert len(result.files_written) == 1
        assert result.files_written[0].name == "AGENTS.md"
        content = (tmp_path / "AGENTS.md").read_text()
        assert "pytest" in content

    def test_empty_recs_no_write(self, tmp_path):
        proj = ProjectInfo(
            name="clean", project_path=tmp_path, data_path=tmp_path
        )
        writer = OpenCodeWriter()
        result = writer.write([], proj, dry_run=False)
        assert result.files_written == []
        assert not (tmp_path / "AGENTS.md").exists()

    def test_dry_run(self, tmp_path):
        proj = ProjectInfo(
            name="test", project_path=tmp_path, data_path=tmp_path
        )
        recs = [
            Recommendation(
                target=RecommendationTarget.CONTEXT_FILE,
                section="Test",
                content="- test",
                confidence=0.8,
                evidence_count=3,
            ),
        ]

        writer = OpenCodeWriter()
        result = writer.write(recs, proj, dry_run=True)

        assert result.dry_run is True
        assert len(result.files_written) == 1
        assert not (tmp_path / "AGENTS.md").exists()

    def test_preserves_existing_content(self, tmp_path):
        agents_md = tmp_path / "AGENTS.md"
        agents_md.write_text("# My Project\n\nExisting instructions.\n")

        proj = ProjectInfo(
            name="test", project_path=tmp_path, data_path=tmp_path
        )
        recs = [
            Recommendation(
                target=RecommendationTarget.CONTEXT_FILE,
                section="Environment",
                content="- Use uv",
                confidence=0.8,
                evidence_count=2,
            ),
        ]

        writer = OpenCodeWriter()
        writer.write(recs, proj, dry_run=False)

        content = agents_md.read_text()
        assert "My Project" in content
        assert "Existing instructions" in content
        assert "Use uv" in content
