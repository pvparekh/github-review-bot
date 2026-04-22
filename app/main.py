import hashlib
import hmac
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from app.reviewer import review_pull_request

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


def _verify_signature(body: bytes, signature: str | None) -> None:
    if not signature or not signature.startswith("sha256="):
        raise HTTPException(status_code=401, detail="Missing webhook signature")
    secret = os.environ["GITHUB_WEBHOOK_SECRET"].encode()
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("GitHub Code Review Bot starting up")
    yield
    log.info("GitHub Code Review Bot shutting down")


app = FastAPI(title="GitHub Code Review Bot", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook")
async def webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    body = await request.body()
    _verify_signature(body, x_hub_signature_256)

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event={x_github_event}"}

    payload = await request.json()
    action = payload.get("action", "")

    if action not in {"opened", "reopened", "synchronize"}:
        return {"status": "ignored", "reason": f"action={action}"}

    repo_full_name: str = payload["repository"]["full_name"]
    pr_number: int = payload["pull_request"]["number"]
    installation_id: int = payload["installation"]["id"]

    log.info("Queuing review for %s #%d (action=%s)", repo_full_name, pr_number, action)
    print(f"BACKGROUND TASK STARTING: {repo_full_name} PR#{pr_number}")
    background_tasks.add_task(review_pull_request, repo_full_name, pr_number, installation_id)

    return {"status": "queued", "pr": pr_number, "repo": repo_full_name}
