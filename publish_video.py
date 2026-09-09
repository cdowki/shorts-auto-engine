"""
[수동 쇼츠 2단계] 직접 찍은 영상 발행기 — 원본 소리 경로

드라이브에 올려둔 세로 영상 하나를 받아
  흐린 배경(정지) + 가운데 영상 + 제목 카드 + 워터마크
로 감싼 뒤 유튜브·릴리스·Make 발행 허브로 보내고 시트에 결과를 되돌려 준다.

기존 render_shorts.py 는 건드리지 않는다. 옆에 나란히 놓인 별도 파일이다.
차이점: 대본·TTS 음성·자막이 없다. 영상의 원본 소리를 그대로 쓴다.
"""

import os
import re
import subprocess
import io
from datetime import datetime, timezone, timedelta
import requests
from PIL import Image, ImageFilter

# Pillow 10 이상에서 삭제된 상수를 moviepy가 참조하므로 호환 처리
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

from moviepy.editor import (
    TextClip, VideoFileClip, ColorClip, ImageClip, CompositeVideoClip
)
from moviepy.video.fx.crop import crop as fx_crop
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# ---------- 기본 설정 (render_shorts.py 와 같은 값) ----------
VIDEO_SIZE = (720, 1280)
WATERMARK = '@비광도기'
TITLE_FONT = 'NanumGothicBold'
CAPTION_FONT = 'NanumGothic'
BLUR_RADIUS = 28
SIDE_PAD = 0.03                   # 영상 좌우 여백 (화면 폭 대비)
YOUTUBE_PRIVACY = 'private'       # private / unlisted / public
YOUTUBE_CATEGORY = '22'

# 이 파일만의 설정
MAX_DURATION = 180                # 네이버 클립 상한 3분. 넘으면 잘라낸다
BAND_BOTTOM = 0.88                # 영상이 들어갈 영역의 아랫변 (워터마크 위)
FILL_WHEN_TALL = True             # 세로 영상은 화면을 꽉 채우고 제목을 그 위에 얹는다
MAX_SPEED = 1.10                  # 속도 조절 상한. 5060 시청자를 생각해 1.1배까지만
NOTICE_SECONDS = 3                # 끝 안내 문구가 화면에 떠 있는 시간
SHADE_OPACITY = 0.32              # 흐린 배경 위에 까는 어둡기


# ---------- 유튜브 업로드 ----------

def upload_to_youtube(file_path, title, description="", tags_text="", privacy=YOUTUBE_PRIVACY):
    """브랜드 채널에 쇼츠 업로드. 성공하면 영상 주소를 돌려준다"""
    client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
    refresh_token = os.environ.get('YOUTUBE_REFRESH_TOKEN')

    if not (client_id and client_secret and refresh_token):
        print("⚠️ YOUTUBE_REFRESH_TOKEN이 없어 유튜브 업로드를 건너뜁니다.")
        return ""

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=['https://www.googleapis.com/auth/youtube.upload']
    )
    youtube = build('youtube', 'v3', credentials=credentials)

    yt_title = str(title)[:95]
    desc = str(description).strip()
    if '#Shorts' not in desc:
        desc = (desc + "\n\n#Shorts").strip()
    yt_desc = desc[:4900]

    tags, total = [], 0
    for t in [x.strip() for x in str(tags_text).split(',') if x.strip()]:
        if total + len(t) + 1 > 450:
            break
        tags.append(t)
        total += len(t) + 1

    body = {
        'snippet': {
            'title': yt_title,
            'description': yt_desc,
            'tags': tags,
            'categoryId': YOUTUBE_CATEGORY
        },
        'status': {
            'privacyStatus': privacy,
            'selfDeclaredMadeForKids': False
        }
    }

    print(f"▶️ 유튜브 업로드 중... (공개설정: {privacy}, 태그 {len(tags)}개)")
    media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True, chunksize=-1)

    try:
        request = youtube.videos().insert(part='snippet,status', body=body, media_body=media)
        response = None
        while response is None:
            status, response = request.next_chunk()

        video_id = response.get('id')
        link = f"https://youtu.be/{video_id}"
        print(f"✅ 유튜브 업로드 성공: {link}")
        print(f"   제목: {yt_title}")
        return link
    except Exception as e:
        print(f"❌ 유튜브 업로드 실패: {e}")
        return ""


# ---------- 시트 콜백 ----------

def send_callback(row, status, video_url="", file_name="", youtube_url="", public_video_url=""):
    """결과를 앱스 스크립트 웹 앱으로 되돌려 보내 시트에 기록"""
    url = os.environ.get('CALLBACK_URL')
    secret = os.environ.get('CALLBACK_SECRET')

    if not url or not secret or not row:
        print("↩️ 콜백 설정이 없어 시트 기록을 건너뜁니다.")
        return

    payload = {
        "secret": secret,
        "row": str(row),
        "status": status,
        "video_url": video_url,
        "file_name": file_name,
        "youtube_url": youtube_url,
        "public_video_url": public_video_url
    }

    try:
        res = requests.post(url, json=payload, timeout=40, allow_redirects=True)
        print(f"↩️ 시트 기록 응답 [{res.status_code}]: {res.text[:160]}")
    except Exception as e:
        print(f"⚠️ 시트 기록 실패(영상은 정상): {e}")


def make_output_name(title, ext=".mp4"):
    """드라이브에서 구분되도록 '날짜_시각_제목' 형식의 파일명 (한국 시간)"""
    safe = re.sub(r'[\\/:*?"<>|\'.,!]', '', str(title)).strip()
    safe = re.sub(r'\s+', '_', safe)[:40].strip('_')
    stamp = datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d_%H%M')
    return f"{stamp}_{safe}{ext}" if safe else f"{stamp}_video{ext}"


# ---------- 구글 드라이브 ----------

def get_drive_service_oauth():
    """개인 계정 OAuth 인증 (영상 내려받기 / 업로드 공용)"""
    client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
    refresh_token = os.environ.get('GOOGLE_OAUTH_REFRESH_TOKEN')

    if not client_id or not client_secret or not refresh_token:
        raise ValueError("❌ GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET / GOOGLE_OAUTH_REFRESH_TOKEN 환경 변수가 없습니다.")

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=credentials)


def download_drive_video(file_id, out_path="source_video.mp4"):
    """드라이브 파일 ID로 영상 하나를 내려받는다. 큰 파일도 견디도록 조각내려받기"""
    if not file_id:
        raise ValueError("❌ VIDEO_FILE_ID가 비어 있습니다.")

    service = get_drive_service_oauth()

    meta = service.files().get(fileId=file_id, fields="name, mimeType, size").execute()
    name = meta.get('name', '')
    mime = str(meta.get('mimeType', ''))
    size = int(meta.get('size', 0) or 0)
    print(f"🎬 원본 영상: {name} ({mime}, {size:,} bytes)")

    if not mime.startswith('video/'):
        raise ValueError(f"❌ 영상 파일이 아닙니다: {mime}")

    request = service.files().get_media(fileId=file_id)
    with io.FileIO(out_path, 'wb') as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=10 * 1024 * 1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"   내려받는 중... {int(status.progress() * 100)}%")

    got = os.path.getsize(out_path)
    print(f"✅ 영상 내려받기 완료: {got:,} bytes")
    if got < 10000:
        raise ValueError("❌ 내려받은 파일이 너무 작습니다.")
    return out_path


def describe_video(path, label):
    """ffprobe 로 크기와 회전 표시를 그대로 찍어 둔다 (진단용)"""
    try:
        out = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=width,height,codec_name'
             ':stream_side_data=rotation:stream_tags=rotate',
             '-of', 'default=noprint_wrappers=1', path],
            capture_output=True, text=True, timeout=60
        ).stdout.strip().replace('\n', ' / ')
        print(f"   🔎 {label}: {out if out else '정보 없음'}")
    except Exception as e:
        print(f"   🔎 {label}: 확인 실패 ({e})")


def normalize_video(src_path, out_path="normalized.mp4"):
    """폰 영상을 반듯한 표준 파일로 다시 만든다.

    폰은 세로로 찍어도 파일 안에는 가로(1920x1080)로 저장하고 "세워서
    재생하라"는 회전 표시만 따로 붙인다. moviepy 1.0.3 은 그 표시를 읽지
    못해 세로 영상을 가로로 착각한다. ffmpeg 으로 한 번 다시 만들면
    회전이 화면에 실제로 적용되고 표시 자체는 사라진다.

    덤으로 HEVC 같은 신형 압축이 표준 H.264 로 바뀌고, 긴 변을 1280 으로
    줄여 뒤따르는 조립 시간이 짧아진다. 결과물은 720x1280 이므로 화질
    손해는 없다.
    """
    print("🧹 원본 영상 정리 중 (회전 적용 · 표준 변환)...")
    describe_video(src_path, "정리 전")

    cmd = [
        'ffmpeg', '-y', '-loglevel', 'error', '-i', src_path,
        '-vf', "scale='min(1280,iw)':'min(1280,ih)"
               "':force_original_aspect_ratio=decrease:force_divisible_by=2",
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac', '-b:a', '128k',
        '-movflags', '+faststart',
        out_path
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) < 10000:
        raise RuntimeError(
            "❌ 영상 정리에 실패했습니다. ffmpeg 메시지: "
            + (proc.stderr or '')[-500:]
        )

    describe_video(out_path, "정리 후")
    print(f"✅ 영상 정리 완료: {os.path.getsize(out_path):,} bytes")
    return out_path


def probe_duration(path):
    """영상 길이를 초로 돌려준다. 못 읽으면 0"""
    try:
        out = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', path],
            capture_output=True, text=True, timeout=60
        ).stdout.strip()
        return float(out)
    except Exception:
        return 0.0


def has_audio(path):
    """소리 트랙이 있는지 확인"""
    try:
        out = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'a:0',
             '-show_entries', 'stream=codec_type',
             '-of', 'default=noprint_wrappers=1:nokey=1', path],
            capture_output=True, text=True, timeout=60
        ).stdout.strip()
        return out.startswith('audio')
    except Exception:
        return False


def run_ffmpeg(cmd, out_path, what):
    """ffmpeg 한 번 돌리고 결과 파일이 제대로 나왔는지 확인"""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    ok = (proc.returncode == 0 and os.path.exists(out_path)
          and os.path.getsize(out_path) > 10000)
    if not ok:
        print(f"   ⚠️ {what} 실패. 원본을 그대로 씁니다.")
        print("      " + (proc.stderr or '')[-300:])
    return ok


def cut_segment(src_path, start, end, out_path="segment.mp4"):
    """영상의 한 구간만 잘라낸다 (여러 편으로 나눠 올릴 때 사용)"""
    length = max(0.5, end - start)
    print(f"✂️ 구간 잘라내기: {start:.1f}초 ~ {end:.1f}초 ({length:.1f}초)")
    cmd = [
        'ffmpeg', '-y', '-loglevel', 'error',
        '-ss', f'{start:.3f}', '-i', src_path, '-t', f'{length:.3f}',
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
        '-movflags', '+faststart', out_path
    ]
    return out_path if run_ffmpeg(cmd, out_path, "구간 잘라내기") else src_path


def detect_silences(path, noise_db, min_len):
    """말이 없는 구간의 (시작, 끝) 목록"""
    proc = subprocess.run(
        ['ffmpeg', '-hide_banner', '-nostats', '-i', path,
         '-af', f'silencedetect=noise={noise_db}dB:d={min_len}', '-f', 'null', '-'],
        capture_output=True, text=True
    )
    log = proc.stderr or ''
    starts = [float(x) for x in re.findall(r'silence_start:\s*(-?[0-9.]+)', log)]
    ends = [float(x) for x in re.findall(r'silence_end:\s*(-?[0-9.]+)', log)]
    total = probe_duration(path)
    pairs = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else total
        if e > s:
            pairs.append((max(0.0, s), min(total, e)))
    return pairs


def remove_silence(src_path, out_path="tight.mp4",
                   noise_db=-30, min_len=0.6, keep_pad=0.15, max_cuts=60):
    """말이 없는 구간을 건너뛰어 영상을 짧게 만든다.

    말끝이 잘리지 않도록 조용한 구간의 앞뒤 0.15초는 남긴다.
    잘라낼 구간이 너무 많으면 긴 것부터 60군데까지만 자른다.
    """
    if not has_audio(src_path):
        print("🤫 소리가 없는 영상이라 무음 제거를 건너뜁니다.")
        return src_path

    total = probe_duration(src_path)
    if total <= 0:
        return src_path

    sil = [(s + keep_pad, e - keep_pad) for s, e in
           detect_silences(src_path, noise_db, min_len)]
    sil = [(s, e) for s, e in sil if e - s >= 0.2]
    if not sil:
        print("🤫 잘라낼 무음 구간이 없습니다.")
        return src_path

    if len(sil) > max_cuts:
        sil = sorted(sil, key=lambda p: p[1] - p[0], reverse=True)[:max_cuts]
        sil.sort()

    keeps, cursor = [], 0.0
    for s, e in sil:
        if s > cursor:
            keeps.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < total:
        keeps.append((cursor, total))
    keeps = [(a, b) for a, b in keeps if b - a >= 0.1]

    if not keeps:
        return src_path

    kept = sum(b - a for a, b in keeps)
    if kept >= total * 0.97:
        print(f"🤫 무음 제거 효과가 작아 건너뜁니다 ({total:.1f}초 → {kept:.1f}초)")
        return src_path

    print(f"🤫 무음 {len(sil)}군데 건너뜀: {total:.1f}초 → 약 {kept:.1f}초")
    expr = '+'.join([f"between(t,{a:.3f},{b:.3f})" for a, b in keeps])
    cmd = [
        'ffmpeg', '-y', '-loglevel', 'error', '-i', src_path,
        '-vf', f"select='{expr}',setpts=N/FRAME_RATE/TB",
        '-af', f"aselect='{expr}',asetpts=N/SR/TB",
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
        '-movflags', '+faststart', out_path
    ]
    if not run_ffmpeg(cmd, out_path, "무음 제거"):
        return src_path
    print(f"   실제 길이: {probe_duration(out_path):.1f}초")
    return out_path


def speed_up(src_path, factor, out_path="fast.mp4"):
    """영상을 조금 빠르게 만든다. 목소리 톤은 그대로 유지된다"""
    factor = max(1.01, min(factor, MAX_SPEED))
    print(f"⏩ {factor:.2f}배 빠르게 (목소리 톤은 그대로)")
    cmd = [
        'ffmpeg', '-y', '-loglevel', 'error', '-i', src_path,
        '-filter:v', f'setpts=PTS/{factor:.4f}',
        '-filter:a', f'atempo={factor:.4f}',
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
        '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k',
        '-movflags', '+faststart', out_path
    ]
    if not run_ffmpeg(cmd, out_path, "속도 조절"):
        return src_path
    print(f"   실제 길이: {probe_duration(out_path):.1f}초")
    return out_path


def fit_duration(src_path, trim_silence='auto', allow_speed=False):
    """180초 안에 들어오도록 줄인다. 줄인 결과 파일 경로와 잘림 여부를 돌려준다"""
    dur = probe_duration(src_path)
    print(f"⏱️ 현재 길이: {dur:.1f}초 (상한 {MAX_DURATION}초)")

    want_silence = (trim_silence == 'on') or (trim_silence == 'auto' and dur > MAX_DURATION)
    if want_silence:
        src_path = remove_silence(src_path)
        dur = probe_duration(src_path)

    if dur > MAX_DURATION and allow_speed:
        src_path = speed_up(src_path, dur / MAX_DURATION * 1.02)
        dur = probe_duration(src_path)

    will_cut = dur > MAX_DURATION + 0.5
    if will_cut:
        print(f"   ⚠️ 아직 {dur:.1f}초입니다. {MAX_DURATION}초에서 잘리고 화면에 안내가 붙습니다.")
    return src_path, will_cut


def upload_to_google_drive(file_path, folder_id, drive_name=None):
    print("☁️ 구글 드라이브 완성 영상 업로드 중...")
    service = get_drive_service_oauth()

    name = drive_name or os.path.basename(file_path)
    file_metadata = {'name': name, 'parents': [folder_id]}
    media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True)

    try:
        file = service.files().create(
            body=file_metadata, media_body=media, fields='id, webViewLink'
        ).execute()
        print(f"✅ 드라이브 업로드 성공: {name}")
        return file.get('webViewLink')
    except Exception as e:
        print(f"❌ 드라이브 업로드 오류: {e}")
        raise e


def upload_to_github_release(file_path, tag_name, title=None):
    """영상을 GitHub 릴리스에 올려 인스타그램이 요구하는 '공개 URL'을 만든다"""
    token = os.environ.get('GH_TOKEN')
    repo = os.environ.get('GH_REPOSITORY')
    if not token or not repo:
        print("⚠️ GH_TOKEN/GH_REPOSITORY가 없어 공개 URL 생성을 건너뜁니다.")
        return ""

    api = f"https://api.github.com/repos/{repo}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    print(f"🔗 GitHub 릴리스 생성 중... (tag: {tag_name})")
    try:
        res = requests.post(f"{api}/releases", headers=headers, json={
            "tag_name": tag_name,
            "name": title or tag_name,
            "body": "수동 쇼츠(영상) - 발행용 임시 공개 영상",
            "draft": False,
            "prerelease": False,
        }, timeout=30)
        res.raise_for_status()
        release = res.json()
    except Exception as e:
        print(f"❌ 릴리스 생성 실패: {e}")
        return ""

    upload_url = release['upload_url'].split('{')[0]
    asset_name = os.path.basename(file_path)

    print(f"📤 영상 업로드 중... ({asset_name})")
    try:
        with open(file_path, 'rb') as f:
            data = f.read()
        up_headers = dict(headers)
        up_headers["Content-Type"] = "video/mp4"
        res = requests.post(f"{upload_url}?name={asset_name}", headers=up_headers, data=data, timeout=180)
        res.raise_for_status()
        public_url = res.json().get('browser_download_url', '')
        print(f"✅ 공개 URL 생성 완료: {public_url}")
        return public_url
    except Exception as e:
        print(f"❌ 영상 업로드(릴리스) 실패: {e}")
        return ""


def publish_via_make_webhook(video_url, caption, blog_link="", threads_text=""):
    """Make 발행 허브 웹훅으로 넘겨 릴스·스레드·틱톡 발행을 위임한다"""
    webhook_url = os.environ.get('MAKE_IG_WEBHOOK_URL')
    if not webhook_url:
        print("⚠️ MAKE_IG_WEBHOOK_URL이 없어 Make 발행 허브 호출을 건너뜁니다.")
        return False

    if not video_url:
        print("⚠️ 공개 영상 URL이 없어 Make 발행 허브 호출을 건너뜁니다.")
        return False

    print("📮 Make 발행 허브로 발행 요청 전송 중...")
    try:
        res = requests.post(webhook_url, json={
            "video_url": video_url,
            "caption": caption,
            "blog_link": blog_link,
            "threads_text": threads_text,
        }, timeout=30)
        res.raise_for_status()
        print(f"✅ Make 발행 허브 전송 완료 (status: {res.status_code})")
        return True
    except Exception as e:
        print(f"❌ Make 발행 허브 전송 실패: {e}")
        return False


# ---------- 글자 카드 (render_shorts.py 와 같은 모양) ----------

def clean_title(text):
    """연출 지시문·특수 기호 제거"""
    text = re.sub(r'\([^)]{1,20}\)', ' ', str(text))
    text = text.replace('*', '')
    text = re.sub(r'\.{2,}|…', ' ', text)
    return re.sub(r'[ \t]+', ' ', text).strip()


def make_text_card(text, fontsize, color, font, size, pad=None, band_opacity=0.62):
    """글자 뒤에 반투명 검은 띠를 깔아 어떤 배경에서도 잘 보이게"""
    if pad is None:
        pad = int(size[0] * 0.032)
    txt = TextClip(text, fontsize=fontsize, color=color, font=font,
                   size=(int(size[0] * 0.86), None), method='caption', align='center')
    band = ColorClip(size=(size[0], txt.h + pad * 2), color=(0, 0, 0)).set_opacity(band_opacity)
    card = CompositeVideoClip(
        [band.set_position(('center', 'center')), txt.set_position(('center', 'center'))],
        size=(size[0], txt.h + pad * 2)
    )
    return card.to_ImageClip(t=0)


def make_watermark_clip(text, size, opacity=0.8):
    """화면 하단에 저자 표기를 작게 고정"""
    fs = int(size[0] * 0.038)
    txt = TextClip(text, fontsize=fs, color='white', font=CAPTION_FONT, method='label')
    pad_x, pad_y = int(fs * 0.9), int(fs * 0.45)
    bg = ColorClip(size=(txt.w + pad_x * 2, txt.h + pad_y * 2), color=(0, 0, 0)).set_opacity(0.45)
    card = CompositeVideoClip(
        [bg.set_position(('center', 'center')), txt.set_position(('center', 'center'))],
        size=(txt.w + pad_x * 2, txt.h + pad_y * 2)
    ).to_ImageClip(t=0)
    return card.set_opacity(opacity)


# ---------- 흐린 배경 ----------

def make_blur_background(video, size, out_path="bg_blur.jpg"):
    """영상의 한 프레임을 뽑아 화면을 꽉 채우도록 자르고 흐리게 만든다.

    매 프레임에 흐림 처리를 하면 45초 영상이 1,000장이 넘어 렌더링이 몇 배로
    늘어나고 깃허브 액션이 시간 초과로 죽는다. 정지 이미지 한 장이면 충분하다.
    """
    W, H = size
    t = min(1.0, max(0.0, video.duration / 2))
    frame = video.get_frame(t)
    im = Image.fromarray(frame).convert('RGB')

    s = max(W / im.width, H / im.height)
    big = im.resize((max(W, int(im.width * s)), max(H, int(im.height * s))), Image.LANCZOS)
    left, top = (big.width - W) // 2, (big.height - H) // 2
    big.crop((left, top, left + W, top + H)).filter(
        ImageFilter.GaussianBlur(BLUR_RADIUS)
    ).save(out_path, quality=88)

    print(f"🌫️ 흐린 배경 생성 완료 (원본 {im.width}x{im.height} → {W}x{H})")
    return out_path


# ---------- 영상 조립 ----------

def build_video(title, src_path, output_path="output_video.mp4", size=None,
                part=1, part_count=1, was_cut=False):
    """흐린 배경 + 가운데 영상 + 제목 카드 + 워터마크 + 끝 안내"""
    print("🎬 영상 조립 시작...")
    size = size or VIDEO_SIZE
    W, H = size

    video = VideoFileClip(src_path)
    print(f"   원본: {video.w}x{video.h}, {video.duration:.1f}초, 소리 {'있음' if video.audio else '없음'}")

    if video.duration > MAX_DURATION:
        print(f"   ⚠️ {MAX_DURATION}초를 넘어 앞부분만 씁니다.")
        video = video.subclip(0, MAX_DURATION)
        was_cut = True
    duration = video.duration

    # 1) 제목 카드 (화면 위쪽 고정)
    title_size = int(W * 0.072)
    title_card = make_text_card(title, title_size, 'yellow', TITLE_FONT, size)
    title_y = int(H * 0.05)
    title_bottom = title_y + title_card.h
    title_clip = title_card.set_position(('center', title_y)).set_duration(duration)

    # 2) 세로 영상이면 화면을 꽉 채운다. 가로·정사각이면 가운데 배치
    fill_screen = FILL_WHEN_TALL and (video.h / video.w) >= (H / W) - 0.01

    if fill_screen:
        # 화면을 덮도록 키운 뒤 넘치는 부분을 가운데 기준으로 잘라낸다
        s = max(W / video.w, H / video.h)
        vw, vh = max(W, int(video.w * s)), max(H, int(video.h * s))
        vid = fx_crop(video.resize((vw, vh)),
                      x_center=vw // 2, y_center=vh // 2, width=W, height=H)
        vid = vid.set_position((0, 0))
        print(f"🧭 세로 영상 → 화면 꽉 채우기 ({video.w}x{video.h} → {vw}x{vh} → {W}x{H})")
    else:
        band_top = title_bottom + int(H * 0.02)
        band_bottom = int(H * BAND_BOTTOM)
        box_w = int(W * (1 - SIDE_PAD * 2))
        box_h = max(1, band_bottom - band_top)
        print(f"🧭 가로 영상 → 가운데 배치. 영역 {band_top} ~ {band_bottom} (높이 {box_h}px)")

        scale = min(box_w / video.w, box_h / video.h, 1.0)
        vw, vh = max(1, int(video.w * scale)), max(1, int(video.h * scale))
        vid = video.resize((vw, vh))
        vid_y = band_top + (box_h - vh) // 2
        vid = vid.set_position(('center', vid_y))
        print(f"   배치: {vw}x{vh}, y={vid_y}")

    # 3) 흐린 배경 (정지) — 꽉 채운 경우에는 영상에 완전히 가려진다
    bg_path = make_blur_background(video, size)
    bg = ImageClip(bg_path).set_duration(duration)
    shade = ColorClip(size=size, color=(0, 0, 0), duration=duration).set_opacity(SHADE_OPACITY)

    layers = [bg, shade, vid, title_clip]

    # 5) 끝 안내 문구 — 다음 편이 있거나, 길이 때문에 잘렸을 때
    notice_text = ""
    if part_count > 1 and part < part_count:
        notice_text = f"{part + 1}편에서 계속"
    elif was_cut:
        notice_text = "영상이 길어 여기까지만 담았습니다"

    if notice_text and duration > NOTICE_SECONDS + 0.5:
        notice = make_text_card(notice_text, int(W * 0.062), 'white', TITLE_FONT, size,
                                band_opacity=0.72)
        notice = (notice.set_position(('center', int(H * 0.60)))
                        .set_start(duration - NOTICE_SECONDS)
                        .set_duration(NOTICE_SECONDS))
        layers.append(notice)
        print(f"📣 끝 안내: \"{notice_text}\" (마지막 {NOTICE_SECONDS}초)")

    if WATERMARK:
        wm = make_watermark_clip(WATERMARK, size)
        wm = wm.set_position(('center', int(H * 0.915) - wm.h // 2)).set_duration(duration)
        layers.append(wm)

    final = CompositeVideoClip(layers, size=size).set_duration(duration)
    if video.audio is not None:
        final = final.set_audio(video.audio)
    else:
        print("   ⚠️ 원본에 소리가 없습니다. 무음 영상으로 만듭니다.")

    final.write_videofile(output_path, fps=24, codec='libx264',
                          audio_codec='aac', preset='veryfast', threads=4)
    print(f"✅ 영상 완성: {output_path}")

    video.close()
    return output_path


# ---------- 실행 ----------

if __name__ == "__main__":
    title = clean_title(os.environ.get('TITLE', '수동 영상 쇼츠'))
    video_file_id = os.environ.get('VIDEO_FILE_ID', '').strip()
    drive_folder_id = os.environ.get('DRIVE_FOLDER_ID')
    row = os.environ.get('ROW', '')
    description = os.environ.get('DESCRIPTION', '')
    tags_text = os.environ.get('TAGS', '')
    blog_link = os.environ.get('BLOG_LINK', '')
    threads_text = " ".join(title.split()).replace("\\", "").replace('"', "'")[:480]

    # 길이 다루기
    def num_env(name, default=0.0):
        try:
            return float(str(os.environ.get(name, '')).strip())
        except Exception:
            return default

    clip_start = max(0.0, num_env('CLIP_START', 0.0))
    clip_end = num_env('CLIP_END', 0.0)
    part = int(num_env('PART', 1) or 1)
    part_count = int(num_env('PART_COUNT', 1) or 1)
    trim_silence = (os.environ.get('TRIM_SILENCE', 'auto').strip().lower() or 'auto')
    if trim_silence not in ('auto', 'on', 'off'):
        trim_silence = 'auto'
    allow_speed = os.environ.get('SPEED_UP', '').strip().lower() == 'on'

    # 시험 모드: 렌더링만 하고 발행은 전부 건너뛴다.
    # 깃허브 화면에서 손으로 돌릴 때만 켜진다 (repository_dispatch 로는 값이 안 들어와 항상 꺼짐)
    dry_run = os.environ.get('DRY_RUN', '').strip().lower() == 'true'

    print(f"📌 제목: {title}")
    print(f"🎞️ 원본 영상 파일 ID: {video_file_id}")
    if row:
        print(f"📄 시트 {row}행")
    if dry_run:
        print("🧪 시험 모드 — 렌더링만 하고 유튜브·드라이브·릴리스·Make·시트 기록을 모두 건너뜁니다.")

    output_file = "output_video.mp4"
    drive_name = make_output_name(title)

    try:
        src = download_drive_video(video_file_id)
        src = normalize_video(src)

        if clip_end > clip_start:
            src = cut_segment(src, clip_start, clip_end)
        elif clip_start > 0:
            src = cut_segment(src, clip_start, probe_duration(src))

        src, was_cut = fit_duration(src, trim_silence=trim_silence, allow_speed=allow_speed)
        build_video(title, src, output_file,
                    part=part, part_count=part_count, was_cut=was_cut)

        if dry_run:
            got = os.path.getsize(output_file) if os.path.exists(output_file) else 0
            print(f"🧪 시험 모드 완료. 결과 파일: {output_file} ({got:,} bytes)")
            print("   아티팩트에서 내려받아 화면을 확인하십시오. 발행은 하지 않았습니다.")
            raise SystemExit(0)

        drive_link = ""
        if drive_folder_id and os.path.exists(output_file):
            drive_link = upload_to_google_drive(output_file, drive_folder_id, drive_name) or ""
        else:
            print("⚠️ DRIVE_FOLDER_ID가 없거나 파일이 없어 드라이브 업로드를 생략합니다.")

        youtube_link = upload_to_youtube(output_file, title, description, tags_text)

        public_video_url = ""
        if os.path.exists(output_file):
            release_tag = f"video-{row or 'r'}-{datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d%H%M%S')}"
            public_video_url = upload_to_github_release(output_file, release_tag, title)

        ig_caption = (description or title).strip() + "\n\n📌 자세한 내용은 프로필 링크를 확인하세요"
        publish_via_make_webhook(public_video_url, ig_caption, blog_link, threads_text)

        send_callback(row, "완료", drive_link, drive_name, youtube_link, public_video_url)

    except Exception as err:
        print(f"❌ 작업 실패: {err}")
        send_callback(row, "실패: " + str(err)[:120], "", "", "")
        raise
