"""Refresh src/tasks/affinity/data/counseling.json from souseha's BD2DB.

    python tools/fetch_souseha_counseling.py            downloads the site's module
    python tools/fetch_souseha_counseling.py FILE.js    reads a saved copy instead

Leo 2026-10-21: the 亲密度谈心 answers come from
https://browndust2-db.souseha.com/cn/affinity?section=counseling and are
written into the tool; the shipped tool reads the saved file and never goes
online.  The site keeps them in one JS module
(assets/affinity-costume-details-<hash>.js, named in main-*.js): per costume
15 questions, each with two answers worth 100 or 80 affinity.  Names come
from the character list (src/tasks/fiend_hunt/data/characters.json).
Dev tool only; needs node.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://browndust2-db.souseha.com"
OUT = ROOT / "src" / "tasks" / "affinity" / "data" / "counseling.json"
CHARACTERS = ROOT / "src" / "tasks" / "fiend_hunt" / "data" / "characters.json"
# The tool reads the 简体 and 繁體 clients only.
LANGUAGES = ("cn", "tw")

NODE_DUMP = """
const details = await import(process.argv[2]);
console.log(JSON.stringify(details.default));
"""


def get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "bd2-auto counseling snapshot"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read().decode("utf-8")


def download_module(folder: Path) -> Path:
    page = get(f"{SITE}/cn/affinity?section=counseling")
    main = re.search(r'src="/assets/(main-[\w-]+\.js)"', page)
    if main is None:
        raise SystemExit("souseha changed its pages: main-*.js not found")
    main_js = get(f"{SITE}/assets/{main.group(1)}")
    module = re.search(r"assets/(affinity-costume-details-[\w-]+\.js)", main_js)
    if module is None:
        raise SystemExit("souseha changed its pages: affinity-costume-details-*.js not found")
    path = folder / "details.mjs"
    path.write_text(get(f"{SITE}/assets/{module.group(1)}"), encoding="utf-8")
    return path


def evaluate(module: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "details.mjs"  # node needs .mjs to read it as a module
        copy.write_text(module.read_text(encoding="utf-8"), encoding="utf-8")
        script = Path(tmp) / "dump.mjs"
        script.write_text(NODE_DUMP, encoding="utf-8")
        result = subprocess.run(
            ["node", str(script), copy.as_uri()],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    return json.loads(result.stdout)


def names() -> dict[str, dict]:
    """costume id -> its character's and costume's names."""
    data = json.loads(CHARACTERS.read_text(encoding="utf-8"))
    found = {}
    for character in data.get("characters") or []:
        for costume in character.get("costumes") or []:
            found[costume["id"]] = {
                "character_zh_cn": character.get("name_zh_cn", ""),
                "character_zh_tw": character.get("name_zh_tw", ""),
                "costume_zh_cn": costume.get("name_zh_cn", ""),
                "costume_zh_tw": costume.get("name_zh_tw", ""),
            }
    return found


def _texts(value: dict) -> dict:
    return {lang: str(value.get(lang, "") or "").strip() for lang in LANGUAGES}


def snapshot(raw: dict) -> dict:
    known = names()
    costumes = []
    for costume_id, detail in raw.items():
        questions = []
        for item in detail.get("counseling") or []:
            choices = sorted(
                item.get("choices") or [], key=lambda c: -int(c.get("affinityExp") or 0)
            )
            if len(choices) < 2:
                continue
            questions.append(
                {
                    "id": item.get("id"),
                    "prompt": _texts(item.get("prompt") or {}),
                    # Best answer first; equal values mean either is right.
                    "answers": [
                        {"text": _texts(c.get("text") or {}), "exp": int(c.get("affinityExp") or 0)}
                        for c in choices
                    ],
                }
            )
        if not questions:
            continue
        entry = {"id": costume_id, **known.get(costume_id, {}), "questions": questions}
        if costume_id not in known:
            print(f"注意：{costume_id} 不在角色名单里，没有名字", file=sys.stderr)
        costumes.append(entry)
    costumes.sort(key=lambda c: c["id"])
    return {
        "source": f"{SITE}/cn/affinity?section=counseling",
        "fetched": date.today().isoformat(),
        "note": "亲密度谈心 answers; refresh with tools/fetch_souseha_counseling.py",
        "costumes": costumes,
    }


def main() -> None:
    if len(sys.argv) > 1:
        raw = evaluate(Path(sys.argv[1]))
    else:
        with tempfile.TemporaryDirectory() as tmp:
            raw = evaluate(download_module(Path(tmp)))
    data = snapshot(raw)
    if not data["costumes"]:
        raise SystemExit("souseha returned no counseling answers; the saved file is kept")
    old_ids = set()
    if OUT.exists():
        old = json.loads(OUT.read_text(encoding="utf-8"))
        old_ids = {c.get("id") for c in old.get("costumes") or []}
        # Same answers: keep the old date so nothing changes.
        if [c for c in old.get("costumes") or []] == data["costumes"]:
            data["fetched"] = old.get("fetched", data["fetched"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    added = [c["id"] for c in data["costumes"] if c["id"] not in old_ids]
    news = f"，新增 {', '.join(added)}" if added else ""
    print(f"谈心题库：{len(data['costumes'])} 套服装{news}")


if __name__ == "__main__":
    main()
