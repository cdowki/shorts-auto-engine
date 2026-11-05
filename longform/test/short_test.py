# short_test.py — 새 틀 숏폼 시험 (쇼츠창 2026-11-05)
# 깃허브 손 실행(short_test.yml)에서만 씀. 실제 쇼츠와 같은 함수(render_shorts.render_new_style)로
# 시험 대본을 영상으로 만들어 릴리스 "shorttest-…"에만 올림 — 유튜브·인스타·틱톡·스레드·클립·시트에는 아무것도 안 함
import json
import os
import sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
import render_shorts as RS  # noqa: E402

items = json.load(open(os.path.join(ROOT, 'longform', 'test', 'short_test.json'), encoding='utf-8'))
only = os.environ.get('ONLY_ROW', '').strip()
tag = 'shorttest-' + datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d%H%M%S')
results = []
for it in items:
    if only and str(it['row']) != only:
        continue
    title = RS.clean_script(it['title'])
    script = RS.clean_script(it['script'])
    out = f"shorttest_{it['row']}.mp4"
    ok = RS.render_new_style(title, script, f"t{it['row']}", out)
    url = RS.upload_to_github_release(out, f"{tag}-{it['row']}", f"새 틀 숏폼 시험 {it['row']}") if ok else ''
    results.append((it['row'], ok, url))
print('\n===== 시험 결과 =====')
for row, ok, url in results:
    print(f"{row}행: {'성공' if ok else '실패(예전 방식으로 갔을 것)'} {url}")
if not all(ok for _, ok, _ in results):
    sys.exit(1)
