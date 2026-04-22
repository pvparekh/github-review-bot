from pydantic import BaseModel
from typing import Literal


class ReviewComment(BaseModel):
    file: str
    position: int
    severity: Literal["critical", "warning", "suggestion"]
    category: Literal["bug", "security", "performance", "style", "best_practice"]
    title: str
    body: str


class ReviewOutput(BaseModel):
    comments: list[ReviewComment]