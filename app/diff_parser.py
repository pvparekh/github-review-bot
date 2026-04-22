import re
from dataclasses import dataclass, field

LANGUAGE_MAP = {
    ".py": "python", ".js": "javascript", ".ts": "typescript",
    ".tsx": "typescript", ".jsx": "javascript", ".java": "java",
    ".go": "go", ".rs": "rust", ".rb": "ruby", ".php": "php",
    ".cs": "csharp", ".cpp": "cpp", ".c": "c", ".h": "c",
    ".hpp": "cpp", ".swift": "swift", ".kt": "kotlin",
    ".sh": "bash", ".yaml": "yaml", ".yml": "yaml",
    ".json": "json", ".toml": "toml", ".sql": "sql",
    ".html": "html", ".css": "css", ".md": "markdown",
}

MAX_PROMPT_CHARS = 12000


@dataclass
class DiffLine:
    content: str
    line_type: str  # "added", "removed", "context"
    diff_position: int


@dataclass
class DiffHunk:
    file_path: str
    language: str
    lines: list[DiffLine] = field(default_factory=list)


def detect_language(file_path: str) -> str:
    ext = "." + file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    return LANGUAGE_MAP.get(ext, "text")


def parse_diff(raw_diff: str) -> list[DiffHunk]:
    hunks: list[DiffHunk] = []
    current_hunk: DiffHunk | None = None
    diff_position = 0

    for line in raw_diff.splitlines():
        if line.startswith("diff --git"):
            diff_position = 0
            current_hunk = None

        elif line.startswith("+++ b/"):
            file_path = line[6:]
            current_hunk = DiffHunk(file_path=file_path, language=detect_language(file_path))
            hunks.append(current_hunk)
            diff_position = 0

        elif line.startswith("@@"):
            if current_hunk is not None:
                diff_position += 1

        elif current_hunk is not None:
            if line.startswith("+") and not line.startswith("+++"):
                diff_position += 1
                current_hunk.lines.append(DiffLine(
                    content=line[1:],
                    line_type="added",
                    diff_position=diff_position,
                ))
            elif line.startswith("-") and not line.startswith("---"):
                diff_position += 1
                current_hunk.lines.append(DiffLine(
                    content=line[1:],
                    line_type="removed",
                    diff_position=diff_position,
                ))
            elif not line.startswith("\\"):
                diff_position += 1
                current_hunk.lines.append(DiffLine(
                    content=line,
                    line_type="context",
                    diff_position=diff_position,
                ))

    return hunks


def format_diff_for_prompt(raw_diff: str) -> str:
    hunks = parse_diff(raw_diff)
    parts: list[str] = []

    for hunk in hunks:
        header = f"### File: {hunk.file_path} (language: {hunk.language})\n"
        lines: list[str] = []
        for dl in hunk.lines:
            prefix = "+" if dl.line_type == "added" else ("-" if dl.line_type == "removed" else " ")
            annotation = f" [pos:{dl.diff_position}]" if dl.line_type == "added" else ""
            lines.append(f"{prefix}{dl.content}{annotation}")
        parts.append(header + "\n".join(lines))

    result = "\n\n".join(parts)
    if len(result) > MAX_PROMPT_CHARS:
        result = result[:MAX_PROMPT_CHARS] + "\n\n[diff truncated — remaining lines omitted]"
    return result
