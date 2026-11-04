"""Daily execution ledger stored as JSON files on a dedicated git branch.

A single file (``ledger.json``) on the ``ledger`` branch holds only the latest
UTC date's record, overwritten each day. It is managed through the GitHub
contents API. Creating or updating a file is a compare-and-swap (create fails if it exists; update requires the current
blob sha), so overlapping runs cannot both claim the same day.

CLI: ``python -m instagram_autoupload.ledger claim|complete``
"""

from __future__ import annotations

import base64
import datetime
import json
import logging
import os
import sys

import requests

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
BRANCH = "ledger"
LEASE = datetime.timedelta(minutes=20)  # longer than the job timeout


def _repo() -> str:
    return os.environ["GITHUB_REPOSITORY"]


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _today() -> str:
    return _now().date().isoformat()


PATH = "ledger.json"


def _ensure_branch() -> None:
    url = f"{GITHUB_API}/repos/{_repo()}/git/ref/heads/{BRANCH}"
    if requests.get(url, headers=_headers(), timeout=30).status_code == 200:
        return
    repo = requests.get(f"{GITHUB_API}/repos/{_repo()}", headers=_headers(), timeout=30)
    repo.raise_for_status()
    default = repo.json()["default_branch"]
    base = requests.get(
        f"{GITHUB_API}/repos/{_repo()}/git/ref/heads/{default}", headers=_headers(), timeout=30
    )
    base.raise_for_status()
    resp = requests.post(
        f"{GITHUB_API}/repos/{_repo()}/git/refs",
        headers=_headers(),
        json={"ref": f"refs/heads/{BRANCH}", "sha": base.json()["object"]["sha"]},
        timeout=30,
    )
    if resp.status_code != 422:  # 422: another run created it first
        resp.raise_for_status()


def _read(date: str) -> tuple[dict | None, str | None]:
    """Return (today's record or None, blob sha of the file for CAS updates)."""
    resp = requests.get(
        f"{GITHUB_API}/repos/{_repo()}/contents/{PATH}",
        headers=_headers(),
        params={"ref": BRANCH},
        timeout=30,
    )
    if resp.status_code == 404:
        return None, None
    resp.raise_for_status()
    body = resp.json()
    record = json.loads(base64.b64decode(body["content"]))
    return (record if record.get("date") == date else None), body["sha"]


def _write(date: str, record: dict, sha: str | None, message: str) -> bool:
    """Create/update the record. Returns False if someone else won the race."""
    payload = {
        "message": message,
        "branch": BRANCH,
        "content": base64.b64encode(json.dumps(record, indent=2).encode()).decode(),
    }
    if sha:
        payload["sha"] = sha
    resp = requests.put(
        f"{GITHUB_API}/repos/{_repo()}/contents/{PATH}",
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    if resp.status_code in (409, 422):
        return False
    resp.raise_for_status()
    return True


def claim() -> bool:
    """Return True if this run should execute the workload."""
    date = _today()
    _ensure_branch()
    for _ in range(3):
        record, sha = _read(date)
        if record and record.get("completed_at"):
            logger.info("%s already completed at %s; skipping", date, record["completed_at"])
            return False
        if record and record.get("started_at"):
            started = datetime.datetime.fromisoformat(record["started_at"])
            if _now() - started < LEASE:
                logger.info("%s claimed at %s and lease still active; skipping", date, record["started_at"])
                return False
        new = {
            "date": date,
            "started_at": _now().isoformat(),
            "completed_at": None,
            "run_id": os.environ.get("GITHUB_RUN_ID"),
            "attempts": (record or {}).get("attempts", 0) + 1,
        }
        if _write(date, new, sha, f"ledger: start {date}"):
            return True
    return False


def complete() -> None:
    date = _today()
    record, sha = _read(date)
    if record is None:
        raise RuntimeError(f"No ledger claim found for {date}")
    record["completed_at"] = _now().isoformat()
    if not _write(date, record, sha, f"ledger: complete {date}"):
        raise RuntimeError("Ledger changed while completing; re-run will skip via post folder state")


def _set_output(key: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            f.write(f"{key}={value}\n")


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if argv[1:] == ["claim"]:
        _set_output("run", "true" if claim() else "false")
    elif argv[1:] == ["complete"]:
        complete()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
