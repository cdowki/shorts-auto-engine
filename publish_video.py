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

def build_video(title, src_path, output_path="output_video.mp4", size=None):
    """흐린 배경 + 가운데 영상 + 제목 카드 + 워터마크"""
    print("🎬 영상 조립 시작...")
    size = size or VIDEO_SIZE
    W, H = size

    video = VideoFileClip(src_path)
    print(f"   원본: {video.w}x{video.h}, {video.duration:.1f}초, 소리 {'있음' if video.audio else '없음'}")

    if video.duration > MAX_DURATION:
        print(f"   ⚠️ {MAX_DURATION}초를 넘어 앞부분만 씁니다.")
        video = video.subclip(0, MAX_DURATION)
    duration = video.duration

    # 1) 제목 카드 (화면 위쪽 고정)
    title_size = int(W * 0.072)
    title_card = make_text_card(title, title_size, 'yellow', TITLE_FONT, size)
    title_y = int(H * 0.05)
    title_bottom = title_y + title_card.h
    title_clip = title_card.set_position(('center', title_y)).set_duration(duration)

    # 2) 영상이 들어갈 영역 = 제목 아래 ~ 워터마크 위
    band_top = title_bottom + int(H * 0.02)
    band_bottom = int(H * BAND_BOTTOM)
    box_w = int(W * (1 - SIDE_PAD * 2))
    box_h = max(1, band_bottom - band_top)
    print(f"🧭 영상 영역: {band_top} ~ {band_bottom} (높이 {box_h}px)")

    # 3) 흐린 배경 (정지)
    bg_path = make_blur_background(video, size)
    bg = ImageClip(bg_path).set_duration(duration)
    shade = ColorClip(size=size, color=(0, 0, 0), duration=duration).set_opacity(SHADE_OPACITY)

    # 4) 영상을 영역 안에 통째로 넣기 (확대는 하지 않음)
    scale = min(box_w / video.w, box_h / video.h, 1.0)
    vw, vh = max(1, int(video.w * scale)), max(1, int(video.h * scale))
    vid = video.resize((vw, vh))
    vid_y = band_top + (box_h - vh) // 2
    vid = vid.set_position(('center', vid_y))
    print(f"   배치: {vw}x{vh}, y={vid_y}")

    layers = [bg, shade, vid, title_clip]
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
        build_video(title, src, output_file)

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
