"""アプリ（GitHub Pages で公開するページ）を組み立てる。

site/index.html と、data の記録（速報・朝のまとめ）を _site フォルダにまとめ、
記録の一覧 manifest.json を作る。ファイル名やアドレスはすべて英数字にする。

使い方: python build_site.py
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

import morning
import ranking

ROOT = Path(__file__).parent
OUT = ROOT / "_site"


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "snapshots").mkdir(parents=True)
    (OUT / "morning").mkdir()
    shutil.copy(ROOT / "site" / "index.html", OUT / "index.html")

    snapshots = []
    for f in sorted(ranking.SNAPSHOT_DIR.glob("*.json"), reverse=True):
        data = json.loads(f.read_text(encoding="utf-8-sig"))
        shutil.copy(f, OUT / "snapshots" / f.name)
        snapshots.append({"file": f"snapshots/{f.name}", "taken_at": data["taken_at"], "timing": data["timing"]})

    mornings = []
    if morning.MORNING_DIR.exists():
        for f in sorted(morning.MORNING_DIR.glob("*.json"), reverse=True):
            data = json.loads(f.read_text(encoding="utf-8-sig"))
            shutil.copy(f, OUT / "morning" / f.name)
            mornings.append({"file": f"morning/{f.name}", "created_at": data["created_at"]})

    manifest = {
        "generated_at": datetime.now(ranking.JST).isoformat(timespec="minutes"),
        "snapshots": snapshots,
        "mornings": mornings,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    print(f"アプリを組み立てました（速報 {len(snapshots)} 回・朝のまとめ {len(mornings)} 日）")


if __name__ == "__main__":
    main()
