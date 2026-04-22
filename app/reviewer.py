import json
import logging
import os
import re
import sys
import traceback
import anthropic
from dotenv import load_dotenv

from app.diff_parser import format_diff_for_prompt
from app.github_client import get_installation_token, get_pr_diff, post_review
from app.models import ReviewComment, ReviewOutput

load_dotenv()

log = logging.getLogger(__name__)

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
_MODEL = "claude-haiku-4-5-20251001"

REVIEW_SYSTEM_PROMPT = """\
You are a senior software engineer performing a thorough code review on a pull request diff.

Rules:
- Review ONLY added lines (marked with +).
- For each issue you find, reference the exact diff position using the [pos:N] annotation shown on each added line.
- Return ONLY valid JSON — no prose, no markdown fences, no explanation outside the JSON.
- JSON schema:
  {
    "comments": [
      {
        "file": "<relative file path>",
        "position": <integer diff position from [pos:N]>,
        "severity": "<critical|warning|suggestion>",
        "category": "<bug|security|performance|style|best_practice>",
        "title": "<short title>",
        "body": "<detailed explanation with suggested fix>"
      }
    ]
  }
- severity: critical = must fix before merge; warning = should fix; suggestion = optional improvement.
- category: bug, security, performance, style, best_practice.
- If you find no issues, return {"comments": []}.
- Do NOT comment on removed lines or context lines.
"""

SUMMARY_SYSTEM_PROMPT = """\
You are a senior software engineer summarizing a pull request review.

Write a concise markdown summary with these sections:
## Overall Assessment
One or two sentences on the quality and purpose of the changes.

## Issues Found
Bullet list of the most important issues (critical first, then warnings, then suggestions). If none, write "None."

## What Looks Good
Bullet list of positive aspects of the changes.

## Recommendation
End with exactly one of:
- **Approve** — ready to merge as-is.
- **Approve with minor fixes** — good changes, small issues to address.
- **Request changes** — significant issues that must be resolved first.
"""


def _extract_json(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else text


def get_inline_comments(diff_text: str) -> list[ReviewComment]:
    formatted = format_diff_for_prompt(diff_text)
    message = _client.messages.create(
        model=_MODEL,
        max_tokens=4096,
        system=REVIEW_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Review this diff:\n\n{formatted}"}],
    )
    raw = message.content[0].text
    try:
        data = json.loads(_extract_json(raw))
        output = ReviewOutput(**data)
        return output.comments
    except Exception:
        log.warning("Failed to parse inline comments JSON: %s", raw[:500])
        return []


def get_review_summary(diff_text: str, comments: list[ReviewComment]) -> str:
    formatted = format_diff_for_prompt(diff_text)
    comment_lines = "\n".join(
        f"- [{c.severity.upper()}] {c.file} pos {c.position}: {c.title}"
        for c in comments
    ) or "None"

    user_content = (
        f"Diff:\n\n{formatted}\n\n"
        f"Inline comments already raised:\n{comment_lines}\n\n"
        "Write the review summary."
    )
    message = _client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=SUMMARY_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return message.content[0].text


def format_comment_body(comment: ReviewComment) -> str:
    severity_emoji = {"critical": "🔴", "warning": "🟡", "suggestion": "🔵"}.get(comment.severity, "⚪")
    category_label = comment.category.replace("_", " ").title()
    return (
        f"{severity_emoji} **{comment.title}**\n"
        f"*{category_label}*\n\n"
        f"{comment.body}"
    )


async def review_pull_request(
    repo_full_name: str,
    pr_number: int,
    installation_id: int,
) -> None:
    print(f"REVIEW TASK STARTED: {repo_full_name} PR#{pr_number}", flush=True)
    sys.stdout.flush()

    try:
        log.info("Starting review: %s #%d", repo_full_name, pr_number)
        print(f"[reviewer] getting installation token for installation_id={installation_id}", flush=True)
        token = get_installation_token(installation_id)

        print(f"[reviewer] fetching diff for {repo_full_name} PR#{pr_number}", flush=True)
        diff = get_pr_diff(repo_full_name, pr_number, token)
        print(f"[reviewer] diff fetched, length={len(diff)}", flush=True)

        print("[reviewer] calling Claude for inline comments", flush=True)
        comments = get_inline_comments(diff)
        print(f"[reviewer] got {len(comments)} inline comments", flush=True)

        print("[reviewer] calling Claude for summary", flush=True)
        summary = get_review_summary(diff, comments)
        print("[reviewer] summary generated", flush=True)

        inline_payload = []
        for c in comments:
            if c.position < 1:
                print(
                    f"[reviewer] skipping comment on {c.file!r} — invalid position={c.position}",
                    flush=True,
                )
                continue
            inline_payload.append({
                "file": c.file,
                "position": c.position,
                "body": format_comment_body(c),
            })

        print(
            f"[reviewer] inline_payload ({len(inline_payload)} valid / {len(comments)} total):",
            flush=True,
        )
        for item in inline_payload:
            print(f"  file={item['file']!r}  position={item['position']}", flush=True)
        sys.stdout.flush()

        print(f"[reviewer] posting review with {len(inline_payload)} comments", flush=True)
        post_review(repo_full_name, pr_number, token, summary, inline_payload)
        log.info("Review posted: %s #%d (%d comments)", repo_full_name, pr_number, len(comments))
        print(f"REVIEW TASK COMPLETE: {repo_full_name} PR#{pr_number}", flush=True)
    except Exception as e:
        print(f"REVIEW TASK ERROR: {type(e).__name__}: {e}", flush=True)
        traceback.print_exc()
        sys.stdout.flush()
        log.exception("Review failed for %s #%d", repo_full_name, pr_number)
