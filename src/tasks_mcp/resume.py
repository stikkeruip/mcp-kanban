"""Resuming parked Claude Code chats: link parsing + terminal launching.

Shared by the adapters (the web view's resume endpoint and the MCP
``resume_task`` tool). Imports nothing from the project — a leaf utility.

Security stance: only the exact ``cd <dir>; claude -r <session-id>`` shape
is ever executed, and the command is rebuilt from parsed parts — raw link
text is never handed to a shell, so a task link cannot smuggle arbitrary
commands.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys

_RESUME_LINK = re.compile(
    r"^cd\s+(?P<dir>.+?)\s*;\s*claude\s+-r\s+(?P<session>[0-9a-fA-F][0-9a-fA-F-]{7,})\s*$"
)


def parse_resume_link(link: str | None) -> tuple[str, str] | None:
    """Return (directory, session_id) if ``link`` is a resume command."""
    if not link:
        return None
    match = _RESUME_LINK.match(link)
    if not match:
        return None
    directory = match.group("dir").strip().strip("'\"")
    return directory, match.group("session")


def launch_terminal(directory: str, session_id: str) -> None:
    """Open a new terminal window running ``claude -r <session_id>`` in
    ``directory`` (resume only works from the session's original cwd)."""
    if sys.platform == "win32":
        if shutil.which("wt.exe"):  # Windows Terminal
            subprocess.Popen(
                ["wt.exe", "-d", directory, "powershell", "-NoExit",
                 "-Command", f"claude -r {session_id}"]
            )
        else:
            subprocess.Popen(
                ["cmd", "/c", "start", "powershell", "-NoExit", "-Command",
                 f"Set-Location -LiteralPath '{directory}'; claude -r {session_id}"]
            )
    elif sys.platform == "darwin":
        script = f'tell app "Terminal" to do script "cd {directory!r} && claude -r {session_id}"'
        subprocess.Popen(["osascript", "-e", script, "-e", 'tell app "Terminal" to activate'])
    else:
        subprocess.Popen(
            ["x-terminal-emulator", "-e",
             f"bash -c 'cd {directory!r} && claude -r {session_id}; exec bash'"]
        )
