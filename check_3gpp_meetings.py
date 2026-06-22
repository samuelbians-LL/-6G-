#!/usr/bin/env python3
"""
检查 3GPP 官方公开会议页的日期、地点和会议编号变化。
不直接修改 published_meetings.json，只写入 pending_updates.json。
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PUBLISHED_FILE = DATA_DIR / "published_meetings.json"
PENDING_FILE = DATA_DIR / "pending_updates.json"

SOURCES = {
    "S1": "https://www.3gpp.org/dynareport?code=Meetings-S1.htm&Itemid=435",
    "S2": "https://www.3gpp.org/dynareport?code=Meetings-S2.htm",
    "R1": "https://www.3gpp.org/dynareport?code=Meetings-R1.htm&Itemid=404",
    "R2": "https://www.3gpp.org/dynareport?code=Meetings-R2.htm",
    "R3": "https://www.3gpp.org/dynareport?code=Meetings-R3.htm",
    "R4": "https://www.3gpp.org/dynareport?code=Meetings-R4.htm",
    "RP": "https://www.3gpp.org/dynareport?code=Meetings-RP.htm&Itemid=402",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; 3GPPMeetingMonitor/1.0)"
}

DATE_PATTERN = re.compile(r"\b(2026-\d{2}-\d{2})\b")
MEETING_PATTERN = re.compile(r"\b([A-Z]{1,2}\d?-\d+(?:-[A-Za-z0-9]+)?)\b")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, content: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(content, file, ensure_ascii=False, indent=2)
        file.write("\n")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_group_page(group: str, url: str) -> list[dict[str, str]]:
    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    records: list[dict[str, str]] = []

    for row in soup.select("tr"):
        text = normalize(row.get_text(" ", strip=True))
        dates = DATE_PATTERN.findall(text)

        if len(dates) < 2:
            continue

        if not dates[0].startswith("2026"):
            continue

        meeting_match = MEETING_PATTERN.search(text)
        if not meeting_match:
            continue

        meeting_id = meeting_match.group(1)
        cells = [normalize(cell.get_text(" ", strip=True)) for cell in row.select("td")]

        # 保守提取地点：通常位于标题之后、起始日期之前。
        city = ""
        if cells:
            for cell in cells:
                if dates[0] in cell:
                    break
                if (
                    cell
                    and meeting_id not in cell
                    and "3GPP" not in cell
                    and "Register" not in cell
                    and "Participants" not in cell
                ):
                    city = cell

        title = next((c for c in cells if "3GPP" in c), f"3GPP {meeting_id}")

        records.append({
            "meeting_id": meeting_id,
            "group": group,
            "title": title,
            "city": city,
            "start": dates[0],
            "end": dates[1],
            "index_url": url
        })

    deduped: dict[str, dict[str, str]] = {}
    for record in records:
        deduped[record["meeting_id"]] = record

    return list(deduped.values())


def compare(published: dict[str, Any], discovered: list[dict[str, str]]) -> list[dict[str, Any]]:
    old_by_id = {m["meeting_id"]: m for m in published.get("meetings", [])}
    pending: list[dict[str, Any]] = []

    for new in discovered:
        old = old_by_id.get(new["meeting_id"])

        if old is None:
            pending.append({
                "type": "NEW_MEETING",
                "meeting_id": new["meeting_id"],
                "group": new["group"],
                "source": new["index_url"],
                "proposed": new
            })
            continue

        changed_fields = {}
        for field in ("title", "city", "start", "end"):
            if normalize(str(old.get(field, ""))) != normalize(str(new.get(field, ""))):
                changed_fields[field] = {
                    "published": old.get(field, ""),
                    "official_page": new.get(field, "")
                }

        if changed_fields:
            pending.append({
                "type": "MEETING_CHANGED",
                "meeting_id": new["meeting_id"],
                "group": new["group"],
                "source": new["index_url"],
                "changes": changed_fields,
                "proposed": new
            })

    return pending


def main() -> int:
    published = load_json(PUBLISHED_FILE)
    discovered: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []

    for group, url in SOURCES.items():
        try:
            discovered.extend(parse_group_page(group, url))
        except requests.RequestException as error:
            errors.append({
                "group": group,
                "source": url,
                "error": str(error)
            })

    updates = compare(published, discovered)
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")

    output = {
        "generated_at": generated_at,
        "count": len(updates),
        "updates": updates,
        "errors": errors
    }

    write_json(PENDING_FILE, output)

    published["last_checked_at"] = generated_at
    write_json(PUBLISHED_FILE, published)

    print(f"检查完成：发现 {len(updates)} 项待核验变化；错误 {len(errors)} 项。")
    return 0


if __name__ == "__main__":
    sys.exit(main())