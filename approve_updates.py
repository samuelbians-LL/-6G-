#!/usr/bin/env python3
"""
人工审核后执行：
python scripts/approve_updates.py --all

将 pending_updates.json 中的 proposed 数据合并到 published_meetings.json。
执行前请先人工检查 pending_updates.json。
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

PUBLISHED_FILE = DATA_DIR / "published_meetings.json"
PENDING_FILE = DATA_DIR / "pending_updates.json"


def load(path: Path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def save(path: Path, payload):
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="批准全部待核验更新")
    args = parser.parse_args()

    if not args.all:
        raise SystemExit("为避免误发布，请显式使用：python scripts/approve_updates.py --all")

    published = load(PUBLISHED_FILE)
    pending = load(PENDING_FILE)

    by_id = {item["meeting_id"]: item for item in published["meetings"]}

    for update in pending.get("updates", []):
        proposed = update.get("proposed")
        if not proposed:
            continue

        meeting_id = proposed["meeting_id"]

        if meeting_id in by_id:
            existing = by_id[meeting_id]
            existing.update({
                "title": proposed["title"],
                "city": proposed["city"],
                "start": proposed["start"],
                "end": proposed["end"],
                "index_url": proposed["index_url"]
            })
        else:
            proposed.update({
                "kind": "WG",
                "description": "自动发现，已人工批准发布。",
                "details_url": proposed["index_url"],
                "report_url": "",
                "tdoc_url": "",
                "files_url": ""
            })
            published["meetings"].append(proposed)

    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    published["published_at"] = now
    published["last_checked_at"] = now
    published["meetings"].sort(key=lambda item: item["start"])

    save(PUBLISHED_FILE, published)
    save(PENDING_FILE, {
        "generated_at": now,
        "count": 0,
        "updates": [],
        "errors": []
    })

    print("已批准并发布待核验更新。")


if __name__ == "__main__":
    main()