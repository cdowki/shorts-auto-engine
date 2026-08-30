import os
import io
import json
import re
import random
import requests
from PIL import Image

# Pillow 10 이상에서 삭제된 상수를 moviepy가 참조하므로 호환 처리
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

from gtts import gTTS
from moviepy.editor import (
    TextClip, AudioFileClip, ColorClip, ImageClip, VideoFileClip,
    CompositeVideoClip
)
from moviepy.video.fx.all import loop as vfx_loop
from googleapiclient.discovery import build
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


VIDEO_SIZE = (1080, 1920)
MAX_CHARS = 45

KEYWORD_MAP = {
    '국민연금': 'retirement', '연금': 'retirement savings', '노후': 'senior couple',
    '은퇴': 'retirement', '퇴직': 'retirement', '보험': 'insurance', '실비': 'insurance',
    '세금': 'tax documents', '절세': 'tax documents', '연말정산': 'tax documents',
    '금융': 'finance', '투자': 'investment chart', '주식': 'stock market', '펀드': 'investment chart',
    '적금': 'savings money', '예금': 'savings money', '통장': 'bank', '은행': 'bank',
    '대출': 'loan document', '이자': 'finance', '카드': 'credit card',
    '부동산': 'real estate', '주택': 'house', '전세': 'apartment', '월세': 'apartment',
    '건강': 'senior health', '병원': 'hospital', '의료': 'hospital',
    '복지': 'community senior', '정부': 'government building', '지원금': 'money cash',
    '블로그': 'blogging laptop', '수익': 'money cash', '부업': 'laptop work',
    '유튜브': 'video camera', '쇼츠': 'smartphone video', '스마트폰': 'smartphone',
    '물가': 'grocery shopping', '생활비': 'grocery shopping', '소비': 'shopping',
    '택배': 'delivery parcel', '일자리': 'working people', '취업': 'office work',
    '여행': 'travel', '운동': 'senior exercise', '식단': 'healthy food',
}
BROAD_KEYWORDS = ['money', 'city', 'people', 'business', 'technology', 'nature']


# ---------- 구글 드라이브 인증 ----------

def get_drive_service():
    """서비스 계정 인증 (오디오 다운로드용, 읽기 전용)"""
    SCOPES = ['https://www.googleapis.com/auth/drive']
    creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not creds_json:
        raise ValueError("❌ GOOGLE_SERVICE_ACCOUNT_JSON 환경 변수가 설정되지 않았습니다.")

    creds_info = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    return build('drive', 'v3', credentials=credentials)


def get_drive_service_oauth():
    """개인 계정 OAuth 인증 (영상 업로드용, 저장공간 있음)"""
    client_id = os.environ.get('GOOGLE_OAUTH_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET')
    refresh_token = os.environ.get('GOOGLE_OAUTH_REFRESH_TOKEN')

    if not client_id or not client_secret or not refresh_token:
        raise ValueError("❌ GOOGLE_OAUTH_CLIENT_ID / GOOGLE_OAUTH_CLIENT_SECRET / GOOGLE_OAUTH_REFRESH_TOKEN 환경 변수가 설정되지 않았습니다.")

    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    return build('drive', 'v3', credentials=credentials)


def download_audio_via_api(file_id, output_path="temp_audio.mp3"):
    print(f"☁️ 구글 API로 오디오 직접 다운로드 시도 중... (ID: {file_id})")
    service = get_drive_service()

    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(output_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while done is False:
        status, done = downloader.next_chunk()

    print(f"✅ 드라이브 API 오디오 다운로드 완료! (크기: {os.path.getsize(output_path)} 바이트)")
    return output_path


def generate_audio(script_text, output_path="temp_audio.mp3"):
    print("🔊 음성(TTS) 생성 중...")
    tts = gTTS(text=script_text, lang='ko')
    tts.save(output_path)
    return output_path


# ---------- 배경 영상 ----------

def extract_keywords(title):
    """한글 제목 -> 픽사베이 검색어 후보 목록 (앞에서부터 순서대로 시도)"""
    matched_ko, hits = [], []
    for ko in sorted(KEYWORD_MAP, key=len, reverse=True):
        if ko in title and not any(ko in m for m in matched_ko):
            matched_ko.append(ko)
            hits.append(KEYWORD_MAP[ko])

    candidates = list(dict.fromkeys(hits))[:3]
    candidates.append(random.choice(BROAD_KEYWORDS))
    candidates.append('nature')
    return list(dict.fromkeys(candidates))


def search_pixabay_video(keyword, api_key, output_path="bg_video.mp4"):
    """Pixabay에서 키워드에 맞는 배경 영상을 검색해 다운로드"""
    try:
        url = "https://pixabay.com/api/videos/"
        params = {
            'key': api_key,
            'q': keyword,
            'video_type': 'film',
            'safesearch': 'true',
            'per_page': 20,
            'order': 'popular'
        }
        response = requests.get(url, params=params, timeout=20)
        if response.status_code != 200:
            print(f"⚠️ Pixabay 응답 코드 {response.status_code}: {response.text[:200]}")
            return None

        hits = response.json().get('hits', [])
        print(f"   검색 결과 {len(hits)}건")
        if not hits:
            return None

        pick = random.choice(hits[:8]) if len(hits) >= 8 else hits[0]
        videos = pick.get('videos', {})
        video_info = videos.get('medium') or videos.get('small') or videos.get('tiny')
        if not video_info or not video_info.get('url'):
            return None

        video_data = requests.get(video_info['url'], timeout=60)
        with open(output_path, 'wb') as f:
            f.write(video_data.content)

        return output_path
    except Exception as e:
        print(f"⚠️ Pixabay 처리 중 오류: {e}")
        return None


def make_gradient_clip(size, duration):
    """PIL로 세로 그라데이션 이미지를 만들어 배경 클립으로 사용"""
    import numpy as np

    w, h = size
    top = np.array([28, 38, 68])
    bottom = np.array([8, 10, 18])

    gradient = np.linspace(0, 1, h).reshape(h, 1, 1)
    img_array = (top * (1 - gradient) + bottom * gradient).astype('uint8')
    img_array = np.repeat(img_array, w, axis=1)

    img_path = "bg_gradient.png"
    Image.fromarray(img_array, 'RGB').save(img_path)

    return ImageClip(img_path).set_duration(duration)


def get_background_clip(title, duration, size=VIDEO_SIZE):
    """제목 키워드로 배경 영상을 찾고, 모두 실패하면 그라데이션 배경 생성"""
    api_key = os.environ.get('PIXABAY_API_KEY')
    video_path = None

    if api_key:
        for keyword in extract_keywords(title):
            print(f"🎥 Pixabay 검색: {keyword}")
            video_path = search_pixabay_video(keyword, api_key)
            if video_path:
                break
    else:
        print("⚠️ PIXABAY_API_KEY가 없어 배경 영상을 건너뜁니다.")

    if video_path and os.path.exists(video_path) and os.path.getsize(video_path) > 10000:
        try:
            print(f"✅ 배경 영상 확보: {os.path.getsize(video_path)} 바이트")
            clip = VideoFileClip(video_path).without_audio()

            w, h = size
            scale = max(w / clip.w, h / clip.h)
            clip = clip.resize(scale)
            clip = clip.crop(x_center=clip.w / 2, y_center=clip.h / 2, width=w, height=h)

            if clip.duration < duration:
                clip = vfx_loop(clip, duration=duration)
            else:
                clip = clip.subclip(0, duration)
            clip = clip.set_duration(duration)

            shade = ColorClip(size=size, color=(0, 0, 0), duration=duration).set_opacity(0.45)
            return CompositeVideoClip([clip, shade], size=size).set_duration(duration)
        except Exception as e:
            print(f"⚠️ 배경 영상 처리 실패, 그라데이션으로 대체: {e}")

    print("🎨 그라데이션 배경을 생성합니다.")
    return make_gradient_clip(size, duration)


# ---------- 자막 ----------

def split_sentences(text):
    """문장 단위 분리 (숫자 뒤 마침표는 분리하지 않음 - 날짜/소수점 보호)"""
    parts = []
    for line in text.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        for s in re.split(r'(?<![0-9])(?<=[.!?])\s+', line):
            s = s.strip()
            if s:
                parts.append(s)
    return parts or [text.strip()]


def chunk_text(sentences, max_chars=MAX_CHARS):
    """긴 문장은 자르고 짧은 문장은 합쳐서 읽기 좋은 자막 카드로 만들기"""
    cards = []
    for s in sentences:
        if len(s) <= max_chars:
            cards.append(s)
            continue
        cur = ''
        for w in s.split(' '):
            if not cur:
                cur = w
            elif len(cur) + 1 + len(w) <= max_chars:
                cur += ' ' + w
            else:
                cards.append(cur)
                cur = w
        if cur:
            cards.append(cur)

    merged = []
    for c in cards:
        if merged and len(merged[-1]) < 14 and len(merged[-1]) + 1 + len(c) <= max_chars:
            merged[-1] = merged[-1] + ' ' + c
        else:
            merged.append(c)
    return merged


def make_text_card(text, fontsize, color, size=VIDEO_SIZE, pad=34, band_opacity=0.62):
    """글자 뒤에 반투명 검은 띠를 깔아 어떤 배경에서도 잘 보이게 만든 자막 묶음"""
    txt = TextClip(
        text,
        fontsize=fontsize,
        color=color,
        font='NanumGothic',
        size=(int(size[0] * 0.85), None),
        method='caption',
        align='center'
    )
    band = ColorClip(size=(size[0], txt.h + pad * 2), color=(0, 0, 0)).set_opacity(band_opacity)
    return CompositeVideoClip(
        [band.set_position(('center', 'center')), txt.set_position(('center', 'center'))],
        size=(size[0], txt.h + pad * 2)
    )


def build_caption_clips(script, duration, size=VIDEO_SIZE):
    """자막 카드를 오디오 길이에 정확히 맞춰 순차 표시"""
    cards = chunk_text(split_sentences(script))
    total = sum(len(c) for c in cards) or 1
    min_seg = min(1.0, duration / max(len(cards), 1))

    raw = [max(duration * len(c) / total, min_seg) for c in cards]
    scale = duration / sum(raw)
    segs = [r * scale for r in raw]

    clips = []
    cursor = 0.0
    for i, (card, seg) in enumerate(zip(cards, segs)):
        end = duration if i == len(cards) - 1 else cursor + seg
        clip = (make_text_card(card, 56, 'white', size)
                .set_position(('center', 'center'))
                .set_start(cursor)
                .set_duration(end - cursor))
        clips.append(clip)
        cursor = end

    print(f"💬 자막 카드 {len(clips)}장 (총 {duration:.1f}초)")
    return clips


# ---------- 영상 렌더링 ----------

def render_video(title, script, audio_path, output_path="output_shorts.mp4"):
    print("🎬 쇼츠 영상 렌더링 시작...")

    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration
    size = VIDEO_SIZE

    bg = get_background_clip(title, duration, size)

    title_clip = (make_text_card(title, 62, 'yellow', size)
                  .set_position(('center', 150))
                  .set_duration(duration))

    caption_clips = build_caption_clips(script, duration, size)

    video = CompositeVideoClip([bg, title_clip] + caption_clips, size=size)
    video = video.set_audio(audio_clip)
    video = video.set_duration(duration)

    video.write_videofile(
        output_path,
        fps=24,
        codec='libx264',
        audio_codec='aac',
        preset='fast'
    )
    print(f"✅ 영상 렌더링 완료: {output_path}")
    return output_path


# ---------- 구글 드라이브 업로드 ----------

def upload_to_google_drive(file_path, folder_id):
    """개인 계정(OAuth)으로 업로드 - 서비스 계정 저장공간 한도 문제 없음"""
    print("☁️ 구글 드라이브 렌더링 영상 업로드 중... (개인 계정 인증)")
    service = get_drive_service_oauth()

    file_metadata = {
        'name': os.path.basename(file_path),
        'parents': [folder_id]
    }
    media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True)

    try:
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()

        print(f"✅ 영상 드라이브 업로드 성공! 파일 ID: {file.get('id')}")
        return file.get('webViewLink')
    except Exception as e:
        print(f"❌ 영상 업로드 오류 발생: {e}")
        raise e


if __name__ == "__main__":
    title = os.environ.get('TITLE', '기본 쇼츠 제목입니다')
    script = os.environ.get('SCRIPT', '여기에 쇼츠 스크립트 내용이 들어갑니다.')
    audio_url = os.environ.get('AUDIO_URL', '')
    drive_folder_id = os.environ.get('DRIVE_FOLDER_ID')

    print(f"📌 타이틀: {title}")
    audio_file = "temp_audio.mp3"

    if audio_url:
        print(f"🔗 전달된 오디오 링크: {audio_url}")
        if "drive.google.com" in audio_url:
            file_id_match = re.search(r'/d/([a-zA-Z0-9_-]+)', audio_url) or re.search(r'id=([a-zA-Z0-9_-]+)', audio_url)
            if file_id_match:
                download_audio_via_api(file_id_match.group(1), audio_file)
            else:
                raise ValueError("❌ 구글 드라이브 링크에서 파일 ID를 추출할 수 없습니다.")
        else:
            response = requests.get(audio_url)
            with open(audio_file, 'wb') as f:
                f.write(response.content)
    else:
        print("🔊 오디오 링크가 없어 기본 TTS를 생성합니다.")
        generate_audio(script, audio_file)

    output_file = "output_shorts.mp4"
    render_video(title, script, audio_file, output_file)

    if drive_folder_id and os.path.exists(output_file):
        upload_to_google_drive(output_file, drive_folder_id)
    else:
        print("⚠️ DRIVE_FOLDER_ID가 없거나 파일이 없어 업로드를 생략합니다.")
