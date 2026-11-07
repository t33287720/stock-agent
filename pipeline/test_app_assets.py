"""檢查 service worker 預快取清單與 manifest 圖示都存在於 app/。"""
import json
import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"


def test_sw_precache_files_exist():
    src = (APP / "sw.js").read_text(encoding="utf-8")
    block = re.search(r"PRECACHE = \[(.*?)\]", src, re.S).group(1)
    files = re.findall(r"'([^']+)'", block)
    assert files
    for f in files:
        assert (APP / f).exists(), f


def test_manifest_icons_exist():
    manifest = json.loads((APP / "manifest.json").read_text(encoding="utf-8"))
    for icon in manifest["icons"]:
        assert (APP / icon["src"]).exists(), icon["src"]
