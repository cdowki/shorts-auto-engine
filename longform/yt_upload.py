# yt_upload.py — 긴 영상 한 편을 유튜브에 올림 (쇼츠창 2026-11-05)
#
# run_daily.js가 부름. 쇼츠(render_shorts.py)와 같은 열쇠·같은 방식으로 올림 — 새 외부 서비스 없음.
#   python3 yt_upload.py --file out/20261105_r1.mp4 --title "쇼츠 제목" --desc-file jobs/20261105_r1/yt_desc.txt [--dry-run]
#   --dry-run : 올리지 않고, 열쇠가 맞는지(토큰 새로 받기)와 올릴 내용만 확인
# 비밀값(환경 변수, 이름만): GOOGLE_OAUTH_CLIENT_ID · GOOGLE_OAUTH_CLIENT_SECRET · YOUTUBE_REFRESH_TOKEN — 값은 찍지 않음
# 마지막 줄에 결과를 한 줄 JSON으로 찍음: {"ok": true, "url": "https://youtu.be/..."} / {"ok": false, "error": "..."}
# 끝 코드: 0 = 올림(또는 시험 통과) · 1 = 실패

import argparse
import json
import os
import sys

PRIVACY = 'public'      # 11/5 비광도기님 결정: 바로 공개 (막는 조건은 run_daily.js가 봄)
CATEGORY = '22'         # 쇼츠와 같음 (22 = 인물/블로그)


def done(ok, **kw):
    print(json.dumps({'ok': ok, **kw}, ensure_ascii=False))
    sys.exit(0 if ok else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--file', required=True)
    ap.add_argument('--title', required=True)
    ap.add_argument('--desc-file', default='')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()

    title = ' '.join(str(a.title).replace('<', '').replace('>', '').split())[:95]
    desc = ''
    if a.desc_file and os.path.exists(a.desc_file):
        with open(a.desc_file, encoding='utf-8') as f:
            desc = f.read().replace('<', '').replace('>', '').strip()[:4900]

    if not title:
        done(False, error='제목이 비어 있음')
    if not os.path.exists(a.file) or os.path.getsize(a.file) < 100 * 1024:
        done(False, error='영상 파일이 없거나 너무 작음')

    cid = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
    csec = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
    rtok = os.environ.get('YOUTUBE_REFRESH_TOKEN')
    if not (cid and csec and rtok):
        done(False, error='유튜브 열쇠(GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET / YOUTUBE_REFRESH_TOKEN)가 없음')

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except Exception as e:
        done(False, error=f'구글 라이브러리 없음: {e}')

    cred = Credentials(
        token=None, refresh_token=rtok, token_uri='https://oauth2.googleapis.com/token',
        client_id=cid, client_secret=csec, scopes=['https://www.googleapis.com/auth/youtube.upload'],
    )

    print(f'제목: {title}')
    print(f'설명: {desc.splitlines()[0] if desc else "(없음)"} … ({len(desc)}자)')
    print(f'공개 범위: {PRIVACY} · AI 표시: 켬 · 아동용 아님 · 파일 {round(os.path.getsize(a.file) / 1048576, 1)}MB')

    if a.dry_run:
        try:
            cred.refresh(Request())
        except Exception as e:
            done(False, error=f'열쇠 확인 실패(토큰 새로 받기): {str(e)[:200]}')
        print('시험: 열쇠 확인 통과 — 올리지 않음')
        done(True, url='', dry=True)

    body = {
        'snippet': {'title': title, 'description': desc, 'tags': [], 'categoryId': CATEGORY},
        'status': {'privacyStatus': PRIVACY, 'selfDeclaredMadeForKids': False, 'containsSyntheticMedia': True},
    }
    try:
        youtube = build('youtube', 'v3', credentials=cred)
        media = MediaFileUpload(a.file, mimetype='video/mp4', resumable=True, chunksize=-1)
        req = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
        resp = None
        while resp is None:
            _, resp = req.next_chunk()
        vid = resp.get('id')
        if not vid:
            done(False, error='올렸지만 영상 번호를 못 받음')
        done(True, url=f'https://youtu.be/{vid}')
    except Exception as e:
        done(False, error=str(e)[:300])


if __name__ == '__main__':
    main()
