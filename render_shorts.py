import os
import re
import random
import subprocess
from datetime import datetime, timezone, timedelta
import requests
from PIL import Image

# Pillow 10 이상에서 삭제된 상수를 moviepy가 참조하므로 호환 처리
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

from gtts import gTTS
from moviepy.editor import (
    TextClip, AudioFileClip, ColorClip, ImageClip, CompositeVideoClip
)
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload

# ---------- 기본 설정 ----------
VIDEO_SIZE = (720, 1280)          # 화질을 높이려면 (1080, 1920) 으로 (렌더링 시간 약 3배)
MAX_CHARS = 45                    # 자막 한 장당 최대 글자수
ZOOM = 0.10                       # 배경 사진이 천천히 다가오는 정도
SPEED = 1.15                      # 음성 배속
MAX_IMAGES = 5                    # 배경 사진 최대 장수
TAIL_SILENCE = 0.4                # 음성 끝에 붙일 무음 길이(초)
KEEP_LOOP_ENDING = True           # 마지막 여운 문장(루프멘트)을 살릴지. False면 잘라냄
TITLE_FONT = 'NanumGothicBold'
CAPTION_FONT = 'NanumGothic'

KEYWORD_MAP = {
    '국민연금': 'retirement', '연금': 'retirement savings', '노후': 'senior couple',
    '은퇴': 'retirement', '퇴직': 'retirement', '보험': 'insurance', '실비': 'insurance',
    '세금': 'tax documents', '절세': 'tax documents', '연말정산': 'tax documents',
    '금융': 'finance', '투자': 'investment chart', '주식': 'stock market',
    '적금': 'savings money', '예금': 'savings money', '통장': 'bank', '은행': 'bank',
    '대출': 'loan document', '이자': 'finance', '카드': 'credit card',
    '부동산': 'real estate', '주택': 'house', '전세': 'apartment', '월세': 'apartment',
    '피로': 'tired senior', '피곤': 'tired senior', '수면': 'sleeping', '불면': 'insomnia',
    '건강': 'senior health', '병원': 'hospital', '의료': 'hospital', '영양제': 'vitamin pills',
    '비타민': 'vitamin pills', '호르몬': 'medical research', '혈당': 'blood sugar test',
    '식단': 'healthy food', '운동': 'senior exercise', '스트레스': 'stressed person',
    '복지': 'community senior', '정부': 'government building', '지원금': 'money cash',
    '블로그': 'blogging laptop', '수익': 'money cash', '부업': 'laptop work',
    '유튜브': 'video camera', '스마트폰': 'smartphone',
    '물가': 'grocery shopping', '생활비': 'grocery shopping', '소비': 'shopping',
    '택배': 'delivery parcel', '일자리': 'working people', '취업': 'office work',
    '여행': 'travel', '중년': 'middle aged', '노화': 'senior portrait',
}
BROAD_KEYWORDS = ['senior lifestyle', 'people', 'nature', 'city']


# ---------- 시트 기록 / 파일명 ----------

def send_callback(row, status, video_url="", file_name=""):
    """렌더링 결과를 앱스 스크립트 웹 앱으로 되돌려 보내 시트에 기록"""
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
        "file_name": file_name
    }

    try:
        res = requests.post(url, json=payload, timeout=40, allow_redirects=True)
        print(f"↩️ 시트 기록 응답 [{res.status_code}]: {res.text[:160]}")
    except Exception as e:
        print(f"⚠️ 시트 기록 실패(영상은 정상): {e}")


def make_output_name(title, ext=".mp4"):
    """드라이브에서 구분되도록 '날짜_시각_제목' 형식의 파일명 만들기 (한국 시간 기준)"""
    safe = re.sub(r'[\\/:*?"<>|\'.,!]', '', str(title)).strip()
    safe = re.sub(r'\s+', '_', safe)[:40].strip('_')
    stamp = datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d_%H%M')
    return f"{stamp}_{safe}{ext}" if safe else f"{stamp}_shorts{ext}"


# ---------- 구글 드라이브 업로드 ----------

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


def upload_to_google_drive(file_path, folder_id, drive_name=None):
    print("☁️ 구글 드라이브 렌더링 영상 업로드 중... (개인 계정 인증)")
    service = get_drive_service_oauth()

    name = drive_name or os.path.basename(file_path)
    file_metadata = {'name': name, 'parents': [folder_id]}
    media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True)

    try:
        file = service.files().create(
            body=file_metadata, media_body=media, fields='id, webViewLink'
        ).execute()
        print(f"✅ 영상 드라이브 업로드 성공: {name}")
        print(f"   파일 ID: {file.get('id')}")
        print(f"   링크: {file.get('webViewLink')}")
        return file.get('webViewLink')
    except Exception as e:
        print(f"❌ 영상 업로드 오류 발생: {e}")
        raise e


# ---------- 대본 정리 ----------

def drop_last_fragment(text):
    """마침표 없이 흐지부지 끝나는 마지막 조각을 잘라냄"""
    t = text.rstrip()
    if t.endswith(('.', '!', '?')):
        return t
    ends = [m.end() for m in re.finditer(r'[.!?]', t)]
    return t[:ends[-1]].strip() if ends else t


def clean_script(text):
    """(진지하게) [강조] **굵게** 같은 연출 지시문 제거. 끝의 여운 표시는 설정에 따라 처리"""
    text = re.sub(r'\([^)]{1,20}\)', ' ', text)
    text = re.sub(r'\[[^\]]{1,20}\]', ' ', text)
    text = text.replace('*', '')

    has_loop_tail = bool(re.search(r'(\.{2,}|\u2026)\s*$', text.rstrip()))

    text = re.sub(r'\.{2,}|\u2026', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text).strip()

    if has_loop_tail:
        text = (text + '...') if KEEP_LOOP_ENDING else drop_last_fragment(text)
    return text


# ---------- 음성 ----------

def generate_audio(script_text, output_path="temp_audio.mp3", speed=SPEED):
    """전체 대본을 gTTS로 생성한 뒤 배속 조정 + 끝에 짧은 무음 추가"""
    # 끝의 말줄임표는 자막에만 필요하고 음성으로 읽으면 잡음이 되므로 제거
    tts_text = re.sub(r'[.\u2026\s]+$', '', script_text).strip()

    print(f"🔊 음성 생성 중... (대본 {len(tts_text)}자)")
    raw_path = "temp_audio_raw.mp3"
    gTTS(text=tts_text, lang='ko').save(raw_path)

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", raw_path,
             "-filter:a", f"atempo={speed},apad=pad_dur={TAIL_SILENCE}",
             "-vn", output_path],
            check=True, capture_output=True
        )
        print(f"✅ 음성 생성 완료 ({speed}배속, 끝 무음 {TAIL_SILENCE}초)")
    except Exception as e:
        print(f"⚠️ 배속 조정 실패, 원본 속도 사용: {e}")
        os.replace(raw_path, output_path)
    return output_path


# ---------- 배경 사진 ----------

def extract_keywords(title, script="", bg_keyword=""):
    """검색어 후보 만들기 - 제미나이가 준 영어 검색어를 1순위로, 없으면 매핑표"""
    given = [k.strip() for k in str(bg_keyword).split(',') if k.strip()]

    matched_ko, hits = [], []
    for source in (title, script[:200]):
        for ko in sorted(KEYWORD_MAP, key=len, reverse=True):
            if ko in source and not any(ko in m for m in matched_ko):
                matched_ko.append(ko)
                hits.append(KEYWORD_MAP[ko])

    candidates = given[:3] + list(dict.fromkeys(hits))[:3]
    candidates.append(random.choice(BROAD_KEYWORDS))
    candidates.append('nature')
    return list(dict.fromkeys(candidates))


def fetch_pixabay_images(keyword, api_key, want):
    """Pixabay 사진 검색 (세로 사진 우선) 후 다운로드"""
    urls = []
    for orientation in ('vertical', 'all'):
        try:
            res = requests.get("https://pixabay.com/api/", timeout=20, params={
                'key': api_key, 'q': keyword, 'image_type': 'photo',
                'orientation': orientation, 'safesearch': 'true',
                'per_page': 30, 'order': 'popular'
            })
            if res.status_code != 200:
                print(f"   ⚠️ 응답 코드 {res.status_code}: {res.text[:120]}")
                continue
            hits = res.json().get('hits', [])
            print(f"   '{keyword}' ({orientation}) 검색 결과 {len(hits)}건")
            pool = [h.get('largeImageURL') for h in hits if h.get('largeImageURL')]
            random.shuffle(pool)
            for u in pool:
                if u not in urls:
                    urls.append(u)
            if len(urls) >= want:
                break
        except Exception as e:
            print(f"   ⚠️ 검색 오류: {e}")

    paths = []
    for u in urls[:want]:
        try:
            data = requests.get(u, timeout=40).content
            if len(data) < 10000:
                continue
            p = f"bg_src_{len(paths)}.jpg"
            with open(p, 'wb') as f:
                f.write(data)
            paths.append(p)
        except Exception as e:
            print(f"   ⚠️ 다운로드 실패: {e}")
    return paths


def collect_background_images(title, script, want, bg_keyword=""):
    """검색어 후보를 순서대로 시도해 배경 사진 확보"""
    api_key = os.environ.get('PIXABAY_API_KEY')
    if not api_key:
        print("⚠️ PIXABAY_API_KEY가 없어 배경 사진을 건너뜁니다.")
        return []

    collected = []
    for keyword in extract_keywords(title, script, bg_keyword):
        print(f"🖼️ Pixabay 검색: {keyword}")
        collected += fetch_pixabay_images(keyword, api_key, want - len(collected))
        if len(collected) >= want:
            break
    print(f"✅ 배경 사진 {len(collected)}장 확보")
    return collected


def prepare_cover_image(src_path, out_path, size, zoom=ZOOM):
    """확대 여유분까지 포함해 화면을 꽉 채우도록 미리 잘라 저장"""
    w = int(size[0] * (1 + zoom))
    h = int(size[1] * (1 + zoom))
    im = Image.open(src_path).convert('RGB')
    scale = max(w / im.width, h / im.height)
    im = im.resize((max(w, int(im.width * scale)), max(h, int(im.height * scale))), Image.LANCZOS)
    left = (im.width - w) // 2
    top = (im.height - h) // 2
    im.crop((left, top, left + w, top + h)).save(out_path, quality=90)
    return out_path


def make_kenburns_clip(img_path, duration, size, zoom=ZOOM):
    """미리 확대해 둔 사진을 서서히 축소해 천천히 다가가는 효과"""
    base = ImageClip(img_path).set_duration(duration)
    moving = base.resize(lambda t: 1.0 - (zoom / (1 + zoom)) * (t / duration))
    return CompositeVideoClip([moving.set_position('center')], size=size).set_duration(duration)


def make_gradient_clip(size, duration):
    """배경 사진을 못 구했을 때 쓰는 그라데이션"""
    import numpy as np
    w, h = size
    top, bottom = np.array([28, 38, 68]), np.array([8, 10, 18])
    g = np.linspace(0, 1, h).reshape(h, 1, 1)
    arr = np.repeat((top * (1 - g) + bottom * g).astype('uint8'), w, axis=1)
    Image.fromarray(arr, 'RGB').save("bg_gradient.png")
    return ImageClip("bg_gradient.png").set_duration(duration)


def build_background(title, script, plan, duration, size, bg_keyword=""):
    """자막이 바뀔 때마다 배경 사진도 바꿔가며 깔기"""
    want = min(len(plan), MAX_IMAGES)
    srcs = collect_background_images(title, script, want, bg_keyword)

    covers = []
    for i, s in enumerate(srcs):
        try:
            covers.append(prepare_cover_image(s, f"bg_cover_{i}.jpg", size))
        except Exception as e:
            print(f"⚠️ 사진 처리 실패({s}): {e}")

    if covers:
        clips = [
            make_kenburns_clip(covers[i % len(covers)], seg, size).set_start(start)
            for i, (_, start, seg) in enumerate(plan)
        ]
        base = CompositeVideoClip(clips, size=size).set_duration(duration)
    else:
        print("🎨 그라데이션 배경을 생성합니다.")
        base = make_gradient_clip(size, duration)

    shade = ColorClip(size=size, color=(0, 0, 0), duration=duration).set_opacity(0.42)
    return CompositeVideoClip([base, shade], size=size).set_duration(duration)


# ---------- 자막 ----------

def split_sentences(text):
    """문장 단위 분리 (숫자 뒤 마침표는 분리하지 않음)"""
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


def _pack(pieces, joiner, max_chars):
    out, cur = [], ''
    for p in pieces:
        if not cur:
            cur = p
        elif len(cur) + len(joiner) + len(p) <= max_chars:
            cur += joiner + p
        else:
            out.append(cur)
            cur = p
    if cur:
        out.append(cur)
    return out


def split_long(s, max_chars):
    """긴 문장 나누기 - 쉼표 경계를 먼저 쓰고, 그래도 길면 띄어쓰기로"""
    if ',' in s:
        parts = [p.strip() for p in s.split(',') if p.strip()]
        result = []
        for piece in _pack(parts, ', ', max_chars):
            result += [piece] if len(piece) <= max_chars else _pack(piece.split(' '), ' ', max_chars)
        return result
    return _pack(s.split(' '), ' ', max_chars)


def chunk_text(sentences, max_chars=MAX_CHARS):
    """긴 문장은 자르고 짧은 문장은 합쳐 읽기 좋은 자막 카드로"""
    cards = []
    for s in sentences:
        if len(s) <= max_chars:
            cards.append(s)
        else:
            cards += split_long(s, max_chars)

    merged = []
    for c in cards:
        if merged and len(merged[-1]) < 14 and len(merged[-1]) + 1 + len(c) <= max_chars:
            merged[-1] = merged[-1] + ' ' + c
        else:
            merged.append(c)
    return merged


def plan_captions(script, duration):
    """자막 카드와 각각의 시작 시각·표시 시간 계산 (합계가 오디오 길이와 정확히 일치)"""
    cards = chunk_text(split_sentences(script))
    total = sum(len(c) for c in cards) or 1
    min_seg = min(1.0, duration / max(len(cards), 1))
    raw = [max(duration * len(c) / total, min_seg) for c in cards]
    scale = duration / sum(raw)
    segs = [r * scale for r in raw]

    plan, cursor = [], 0.0
    for i, (c, seg) in enumerate(zip(cards, segs)):
        end = duration if i == len(cards) - 1 else cursor + seg
        plan.append((c, cursor, end - cursor))
        cursor = end
    return plan


def make_text_card(text, fontsize, color, font, size, pad=None, band_opacity=0.62):
    """글자 뒤에 반투명 검은 띠를 깔아 어떤 배경에서도 잘 보이게 (정지 이미지로 굳힘)"""
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


# ---------- 영상 렌더링 ----------

def render_video(title, script, audio_path, output_path="output_shorts.mp4", size=None, bg_keyword=""):
    print("🎬 쇼츠 영상 렌더링 시작...")
    size = size or VIDEO_SIZE
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration

    title_size = int(size[0] * 0.072)
    caption_size = int(size[0] * 0.052)

    plan = plan_captions(script, duration)
    print(f"💬 자막 카드 {len(plan)}장 (총 {duration:.1f}초)")

    bg = build_background(title, script, plan, duration, size, bg_keyword)

    # 제목은 화면 위쪽 고정
    title_card = make_text_card(title, title_size, 'yellow', TITLE_FONT, size)
    title_y = int(size[1] * 0.05)
    title_clip = title_card.set_position(('center', title_y)).set_duration(duration)

    # 자막은 화면 중앙, 단 제목과 겹치면 아래로 밀고 화면 밖으로 나가면 위로 당김
    gap = int(size[1] * 0.05)
    title_bottom = title_y + title_card.h
    bottom_margin = int(size[1] * 0.06)

    caption_clips = []
    for text, start, seg in plan:
        card = make_text_card(text, caption_size, 'white', CAPTION_FONT, size)
        y = (size[1] - card.h) // 2
        y = max(y, title_bottom + gap)
        y = min(y, size[1] - bottom_margin - card.h)
        caption_clips.append(
            card.set_position(('center', y)).set_start(start).set_duration(seg)
        )

    video = CompositeVideoClip([bg, title_clip] + caption_clips, size=size)
    video = video.set_audio(audio_clip).set_duration(duration)
    video.write_videofile(output_path, fps=24, codec='libx264',
                          audio_codec='aac', preset='veryfast', threads=4)
    print(f"✅ 영상 렌더링 완료: {output_path}")
    return output_path


if __name__ == "__main__":
    title = clean_script(os.environ.get('TITLE', '기본 쇼츠 제목입니다'))
    script = clean_script(os.environ.get('SCRIPT', '여기에 쇼츠 스크립트 내용이 들어갑니다.'))
    drive_folder_id = os.environ.get('DRIVE_FOLDER_ID')
    bg_keyword = os.environ.get('BG_KEYWORD', '')
    row = os.environ.get('ROW', '')

    print(f"📌 타이틀: {title}")
    if bg_keyword:
        print(f"🔑 제미나이 배경 검색어: {bg_keyword}")
    if row:
        print(f"📄 시트 {row}행")

    output_file = "output_shorts.mp4"
    drive_name = make_output_name(title)

    try:
        audio_file = generate_audio(script)
        render_video(title, script, audio_file, output_file, bg_keyword=bg_keyword)

        if drive_folder_id and os.path.exists(output_file):
            link = upload_to_google_drive(output_file, drive_folder_id, drive_name)
            send_callback(row, "완료", link or "", drive_name)
        else:
            print("⚠️ DRIVE_FOLDER_ID가 없거나 파일이 없어 업로드를 생략합니다.")
            send_callback(row, "업로드 생략", "", drive_name)

    except Exception as err:
        print(f"❌ 작업 실패: {err}")
        send_callback(row, "실패: " + str(err)[:120], "", "")
        raise
