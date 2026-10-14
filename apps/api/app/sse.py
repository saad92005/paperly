"""Server-sent event formatting."""

import json


def sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"
