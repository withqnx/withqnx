#!/usr/bin/env python3
"""intel_data.json 을 template.html 에 끼워 대시보드 페이지를 만든다.
  python3 intel/render.py               → intel/후기_인텔리전스.html (아티팩트용, 문서 머리 없음)
  python3 intel/render.py --site OUT    → OUT (실제 사이트용, doctype·charset·viewport 포함)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(f"{HERE}/intel_data.json", encoding="utf-8"))
blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
html = open(f"{HERE}/template.html", encoding="utf-8").read().replace("__DATA__", blob)
if "--site" in sys.argv:
    out = sys.argv[sys.argv.index("--site") + 1]
    # 입장 비밀번호는 레포에 따로 두지 않고 관리자 화면(index.html)에 있는 값을 빌드 때 그대로 가져온다.
    import re
    src = open(os.path.join(os.path.dirname(HERE), "index.html"), encoding="utf-8").read()
    g = re.search(r"const GATE_PWD\s*=\s*'([^']*)'", src); a = re.search(r"const ADMIN_PWD\s*=\s*'([^']*)'", src)
    if not (g and a):
        sys.exit("관리자 화면에서 입장 비밀번호를 찾지 못해 빌드를 멈춘다(잠금 없는 화면을 배포하지 않기 위해).")
    gate = "<script>window.__GATE__=" + json.dumps({"g": g.group(1), "a": a.group(1)}) + "</script>"
    html = gate + html
    html = ('<!doctype html><html lang="ko"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
            '<style>body{margin:0}[hidden]{display:none!important}</style></head><body>' + html + '</body></html>')
else:
    out = f"{HERE}/후기_인텔리전스.html"
open(out, "w", encoding="utf-8").write(html)
print(out, os.path.getsize(out) // 1024, "KB")
