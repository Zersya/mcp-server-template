import os
import time
import traceback
from typing import Any, Dict, Callable

from job_queue import JobQueue

# Import long-running functions from server module
# These functions already handle their own notifications via notify_status
from server import (
    instagram_scrape,
    image_generate_ideogram,
    image_edit_replicate,
    instagram_generate_and_edit,
)

JOB_DB_PATH = os.environ.get("JOB_DB_PATH", "jobs.db")
POLL_INTERVAL_SEC = float(os.environ.get("JOB_POLL_INTERVAL", "1.0"))

queue = JobQueue(JOB_DB_PATH)


def _handler_instagram_scrape(payload: Dict[str, Any]) -> Dict[str, Any]:
    return instagram_scrape(**payload)


def _handler_image_generate_ideogram(payload: Dict[str, Any]) -> Dict[str, Any]:
    return image_generate_ideogram(**payload)


def _handler_image_edit_replicate(payload: Dict[str, Any]) -> Dict[str, Any]:
    return image_edit_replicate(**payload)


def _handler_instagram_generate_and_edit(payload: Dict[str, Any]) -> Dict[str, Any]:
    return instagram_generate_and_edit(**payload)


HANDLERS: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "instagram_scrape": _handler_instagram_scrape,
    "image_generate_ideogram": _handler_image_generate_ideogram,
    "image_edit_replicate": _handler_image_edit_replicate,
    "instagram_generate_and_edit": _handler_instagram_generate_and_edit,
}


def process_one() -> bool:
    job = queue.reserve_one()
    if not job:
        return False

    handler = HANDLERS.get(job.type)
    if not handler:
        queue.fail(job.id, f"No handler for job type '{job.type}'")
        return True

    try:
        payload = job.payload
        # payload is a JSON string; worker relies on server-side handlers
        import json
        data = json.loads(payload) if isinstance(payload, str) else payload
        result = handler(data)
        queue.complete(job.id, result)
    except Exception as e:
        tb = traceback.format_exc()[-5000:]
        queue.fail(job.id, f"{e}\n{tb}")
    return True


def run_forever() -> None:
    print(f"[worker] Starting worker. DB={JOB_DB_PATH}")
    while True:
        did_work = process_one()
        if not did_work:
            time.sleep(POLL_INTERVAL_SEC)


if __name__ == "__main__":
    run_forever()

