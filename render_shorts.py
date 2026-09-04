import os
import re
import random
import subprocess
import time
from datetime import datetime, timezone, timedelta
import requests
from PIL import Image, ImageFilter

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
YOUTUBE_PRIVACY = 'private'       # private(비공개) / unlisted(일부공개) / public(공개)
YOUTUBE_CATEGORY = '22'           # 22=인물/블로그, 27=교육
WATERMARK = '@비광도기'           # 화면 하단에 고정 표시할 저자 표기 (빈 문자열이면 표시 안 함)
TITLE_FONT = 'NanumGothicBold'
CAPTION_FONT = 'NanumGothic'

CAPTION_BOTTOM = 0.82             # 자막 카드 아랫변 위치 (화면 높이 대비)
BLUR_RADIUS = 28                  # 블로그 이미지 뒤에 까는 흐린 배경의 흐림 정도
SIDE_PAD = 0.03                   # 블로그 이미지 좌우 여백 (화면 폭 대비)
MIN_BAND_H = 200                  # 이 높이보다 좁으면 블러 레이아웃을 포기하고 꽉 채우기로 전환
EDGE_TRIM = 0.025                 # 원본 사진 테두리를 살짝 잘라내는 비율 (흰 여백·둥근 모서리 등 아티팩트 제거용)

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

    # 유튜브 제한: 제목 100자, 설명 5000자, 태그 합계 500자
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
    """드라이브에서 구분되도록 '날짜_시각_제목' 형식의 파일명 만들기 (한국 시간 기준)"""
    safe = re.sub(r'[\\/:*?"<>|\'.,!]', '', str(title)).strip()
    safe = re.sub(r'\s+', '_', safe)[:40].strip('_')
    stamp = datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d_%H%M')
    return f"{stamp}_{safe}{ext}" if safe else f"{stamp}_shorts{ext}"


# ---------- 구글 드라이브 ----------

def get_drive_service_oauth():
    """개인 계정 OAuth 인증 (영상 업로드 / 블로그 이미지 내려받기 공용)"""
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


def upload_to_github_release(file_path, tag_name, title=None):
    """영상을 GitHub 릴리스에 올려 인스타그램 API가 요구하는 '공개 URL'을 만든다"""
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
            "body": "쇼츠 자동화 - 인스타그램 발행용 임시 공개 영상",
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
        res = requests.post(f"{upload_url}?name={asset_name}", headers=up_headers, data=data, timeout=120)
        res.raise_for_status()
        public_url = res.json().get('browser_download_url', '')
        print(f"✅ 공개 URL 생성 완료: {public_url}")
        return public_url
    except Exception as e:
        print(f"❌ 영상 업로드(릴리스) 실패: {e}")
        return ""


def publish_to_instagram(video_url, caption):
    """인스타그램 릴스 발행 (컨테이너 생성 → 처리 대기 → 발행). IG_PUBLISH=true 아니면 실제 발행 전 단계에서 멈춤(드라이런)"""
    ig_user_id = os.environ.get('IG_USER_ID')
    access_token = os.environ.get('IG_ACCESS_TOKEN')

    if not ig_user_id or not access_token:
        print("⚠️ IG_USER_ID/IG_ACCESS_TOKEN이 없어 인스타그램 발행을 건너뜁니다. (0단계 미완료)")
        return ""

    if not video_url:
        print("⚠️ 공개 영상 URL이 없어 인스타그램 발행을 건너뜁니다.")
        return ""

    dry_run = os.environ.get('IG_PUBLISH', 'false').strip().lower() != 'true'
    api_ver = "v21.0"

    print("📦 인스타그램 릴스 컨테이너 생성 중...")
    try:
        res = requests.post(f"https://graph.facebook.com/{api_ver}/{ig_user_id}/media", data={
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": access_token,
        }, timeout=30)
        res.raise_for_status()
        container_id = res.json().get("id")
    except Exception as e:
        print(f"❌ 인스타그램 컨테이너 생성 실패: {e}")
        return ""

    print(f"⏳ 인스타그램 영상 처리 대기 중... (container: {container_id})")
    status = ""
    for _ in range(30):  # 최대 5분 (10초 x 30회)
        time.sleep(10)
        try:
            res = requests.get(f"https://graph.facebook.com/{api_ver}/{container_id}", params={
                "fields": "status_code",
                "access_token": access_token,
            }, timeout=30)
            res.raise_for_status()
            status = res.json().get("status_code", "")
            print(f"   상태: {status}")
            if status == "FINISHED":
                break
            if status == "ERROR":
                print("❌ 인스타그램 영상 처리 실패 (ERROR)")
                return ""
        except Exception as e:
            print(f"⚠️ 인스타그램 상태 확인 실패: {e}")

    if status != "FINISHED":
        print("❌ 인스타그램 영상 처리 시간 초과")
        return ""

    if dry_run:
        print(f"🧪 IG_PUBLISH=true가 아니라서 드라이런으로 멈춥니다. (container_id: {container_id})")
        return f"[DRY-RUN] {container_id}"

    print("🚀 인스타그램 릴스 발행 중...")
    try:
        res = requests.post(f"https://graph.facebook.com/{api_ver}/{ig_user_id}/media_publish", data={
            "creation_id": container_id,
            "access_token": access_token,
        }, timeout=30)
        res.raise_for_status()
        media_id = res.json().get("id")
        print(f"✅ 인스타그램 릴스 발행 완료! (media_id: {media_id})")
        return media_id
    except Exception as e:
        print(f"❌ 인스타그램 발행 실패: {e}")
        return ""


def publish_via_make_webhook(video_url, caption):
    """Make.com 발행 허브 웹훅으로 공개 영상 URL과 캡션을 보내 인스타그램 릴스 발행을 위임한다.
    (Meta 개발자 앱 등록 없이 Make의 승인된 앱을 거쳐 발행 — 0단계 버그 우회용, 2026-09-04 추가)"""
    webhook_url = os.environ.get('MAKE_IG_WEBHOOK_URL')
    if not webhook_url:
        print("⚠️ MAKE_IG_WEBHOOK_URL이 없어 Make 발행 허브 호출을 건너뜁니다.")
        return False

    if not video_url:
        print("⚠️ 공개 영상 URL이 없어 Make 발행 허브 호출을 건너뜁니다.")
        return False

    print("📮 Make 발행 허브로 인스타그램 릴스 발행 요청 전송 중...")
    try:
        res = requests.post(webhook_url, json={
            "video_url": video_url,
            "caption": caption,
        }, timeout=30)
        res.raise_for_status()
        print(f"✅ Make 발행 허브 전송 완료 (status: {res.status_code})")
        return True
    except Exception as e:
        print(f"❌ Make 발행 허브 전송 실패: {e}")
        return False


def _natural_key(name):
    """image_2 가 image_10 보다 앞에 오도록 숫자를 숫자로 비교"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', name)]


def download_drive_images(folder_id, want=MAX_IMAGES):
    """블로그 글에 쓴 제미나이 생성 이미지를 드라이브 폴더에서 내려받기 (표지 카드는 제외)"""
    if not folder_id:
        return []

    print(f"🖼️ 블로그 이미지 폴더 조회: {folder_id}")
    try:
        service = get_drive_service_oauth()
        res = service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id, name, mimeType)",
            pageSize=200
        ).execute()
        files = res.get('files', [])
    except Exception as e:
        print(f"⚠️ 이미지 폴더 조회 실패: {e}")
        return []

    images = [f for f in files if str(f.get('mimeType', '')).startswith('image/')]
    # cover.png 는 제목이 적힌 표지 카드라 배경으로 쓰면 글자가 겹친다
    body = [f for f in images if not f['name'].lower().startswith('cover')]
    picked = sorted(body or images, key=lambda f: _natural_key(f['name']))[:want]

    if not picked:
        print(f"⚠️ 폴더에 쓸 만한 이미지가 없습니다. (파일 {len(files)}개)")
        return []

    paths = []
    for f in picked:
        try:
            data = service.files().get_media(fileId=f['id']).execute()
            if not data or len(data) < 3000:
                print(f"   ⚠️ 너무 작아 건너뜀: {f['name']}")
                continue
            ext = os.path.splitext(f['name'])[1].lower() or '.png'
            p = f"blog_img_{len(paths)}{ext}"
            with open(p, 'wb') as fp:
                fp.write(data)
            paths.append(p)
            print(f"   ✅ {f['name']} ({len(data):,} bytes)")
        except Exception as e:
            print(f"   ⚠️ 내려받기 실패({f['name']}): {e}")

    print(f"✅ 블로그 이미지 {len(paths)}장 확보")
    return paths


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

    has_loop_tail = bool(re.search(r'(\.{2,}|…)\s*$', text.rstrip()))

    text = re.sub(r'\.{2,}|…', ' ', text)
    text = re.sub(r'[ \t]+', ' ', text).strip()

    if has_loop_tail:
        text = (text + '...') if KEEP_LOOP_ENDING else drop_last_fragment(text)
    return text


# ---------- 음성 ----------

def generate_audio(script_text, output_path="temp_audio.mp3", speed=SPEED):
    """전체 대본을 gTTS로 생성한 뒤 배속 조정 + 끝에 짧은 무음 추가"""
    # 끝의 말줄임표는 자막에만 필요하고 음성으로 읽으면 잡음이 되므로 제거
    tts_text = re.sub(r'[.…\s]+$', '', script_text).strip()

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


# ---------- 배경 사진 (예비: Pixabay) ----------

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
    """Pixabay 사진 검색 (세로 사진 우선) 후 다운로드. 검색 순위를 그대로 지켜 관련도를 유지"""
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
            for h in hits:
                u = h.get('largeImageURL')
                if u and u not in urls:
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
            p = f"bg_src_{random.randint(100000, 999999)}.jpg"
            with open(p, 'wb') as f:
                f.write(data)
            paths.append(p)
        except Exception as e:
            print(f"   ⚠️ 다운로드 실패: {e}")
    return paths


def collect_background_images(title, script, want, bg_keyword=""):
    """검색어 후보를 순서대로 시도해 배경 사진 확보 (한 검색어가 전부 차지하지 않도록 나눠 담음)"""
    api_key = os.environ.get('PIXABAY_API_KEY')
    if not api_key:
        print("⚠️ PIXABAY_API_KEY가 없어 배경 사진을 건너뜁니다.")
        return []

    keywords = extract_keywords(title, script, bg_keyword)
    per_keyword = max(1, -(-want // max(1, min(3, len(keywords)))))  # 올림 나눗셈

    collected = []
    for keyword in keywords:
        if len(collected) >= want:
            break
        print(f"🖼️ Pixabay 검색: {keyword}")
        need = min(per_keyword, want - len(collected))
        collected += fetch_pixabay_images(keyword, api_key, need)

    print(f"✅ 배경 사진 {len(collected)}장 확보")
    return collected[:want]


# ---------- 배경 이미지 가공 ----------

def prepare_cover_image(src_path, out_path, size, zoom=ZOOM):
    """확대 여유분까지 포함해 화면을 꽉 채우도록 미리 잘라 저장 (Pixabay 사진용)"""
    w = int(size[0] * (1 + zoom))
    h = int(size[1] * (1 + zoom))
    im = Image.open(src_path).convert('RGB')
    scale = max(w / im.width, h / im.height)
    im = im.resize((max(w, int(im.width * scale)), max(h, int(im.height * scale))), Image.LANCZOS)
    left = (im.width - w) // 2
    top = (im.height - h) // 2
    im.crop((left, top, left + w, top + h)).save(out_path, quality=90)
    return out_path


def prepare_blur_fit(src_path, out_bg, out_fg, size, band, zoom=ZOOM, side_pad=SIDE_PAD, edge_trim=EDGE_TRIM):
    """사진을 자르지 않고 통째로 넣고, 남는 곳은 같은 사진을 흐리게 깔아 채운다 (블로그 이미지용)"""
    W, H = size
    band_top, band_bottom = band
    box_w = int(W * (1 - side_pad * 2))
    box_h = max(1, band_bottom - band_top)

    im = Image.open(src_path).convert('RGB')

    # 원본 테두리를 살짝 잘라내고 시작 (흰 여백·둥근 모서리 같은 아티팩트가
    # 선명한 원본 가장자리에 그대로 보이는 문제 방지)
    if edge_trim > 0:
        w0, h0 = im.size
        tx, ty = int(w0 * edge_trim), int(h0 * edge_trim)
        if w0 - tx * 2 > 0 and h0 - ty * 2 > 0:
            im = im.crop((tx, ty, w0 - tx, h0 - ty))

    # 1) 흐린 배경: 화면을 꽉 채우도록 잘라서 블러 (확대 여유분 포함)
    bw, bh = int(W * (1 + zoom)), int(H * (1 + zoom))
    s = max(bw / im.width, bh / im.height)
    big = im.resize((max(bw, int(im.width * s)), max(bh, int(im.height * s))), Image.LANCZOS)
    left, top = (big.width - bw) // 2, (big.height - bh) // 2
    big.crop((left, top, left + bw, top + bh)).filter(
        ImageFilter.GaussianBlur(BLUR_RADIUS)
    ).save(out_bg, quality=88)

    # 2) 선명한 원본: 지정 영역 안에 통째로 들어가게 맞춤 (너무 흐려지지 않게 1.5배까지만 확대)
    s2 = min(box_w / im.width, box_h / im.height, 1.5)
    fw, fh = max(1, int(im.width * s2)), max(1, int(im.height * s2))
    im.resize((fw, fh), Image.LANCZOS).save(out_fg, quality=95)

    fg_y = band_top + (box_h - fh) // 2
    return out_bg, out_fg, fg_y


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


def build_background(title, script, plan, duration, size, bg_keyword="",
                     image_folder_id="", band=None):
    """1순위: 블로그 글의 제미나이 이미지(잘리지 않게) / 2순위: Pixabay 사진(꽉 채우기) / 3순위: 그라데이션"""
    want = min(len(plan), MAX_IMAGES)

    srcs = download_drive_images(image_folder_id, want) if image_folder_id else []
    use_fit = bool(srcs) and band is not None and (band[1] - band[0]) >= MIN_BAND_H

    if srcs and not use_fit:
        print("ℹ️ 자막 영역이 좁아 블로그 이미지도 꽉 채우기로 표시합니다.")

    if not srcs:
        if image_folder_id:
            print("↩️ 블로그 이미지를 못 써서 Pixabay로 대체합니다.")
        srcs = collect_background_images(title, script, want, bg_keyword)
        use_fit = False

    shade_opacity = 0.32 if use_fit else 0.42

    if use_fit:
        prepared = []
        for i, s in enumerate(srcs):
            try:
                prepared.append(prepare_blur_fit(s, f"bg_blur_{i}.jpg", f"bg_fit_{i}.jpg", size, band))
            except Exception as e:
                print(f"⚠️ 이미지 처리 실패({s}): {e}")

        if prepared:
            blur_clips, fit_clips = [], []
            for i, (_, start, seg) in enumerate(plan):
                bg_path, fg_path, fg_y = prepared[i % len(prepared)]
                blur_clips.append(make_kenburns_clip(bg_path, seg, size).set_start(start))
                fit_clips.append(
                    ImageClip(fg_path).set_start(start).set_duration(seg)
                    .set_position(('center', fg_y))
                )
            shade = ColorClip(size=size, color=(0, 0, 0), duration=duration).set_opacity(shade_opacity)
            return CompositeVideoClip(blur_clips + [shade] + fit_clips, size=size).set_duration(duration)
        print("⚠️ 블로그 이미지 가공에 모두 실패해 꽉 채우기로 되돌립니다.")

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


# ---------- 영상 렌더링 ----------

def render_video(title, script, audio_path, output_path="output_shorts.mp4", size=None,
                 bg_keyword="", image_folder_id=""):
    print("🎬 쇼츠 영상 렌더링 시작...")
    size = size or VIDEO_SIZE
    W, H = size
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration

    title_size = int(W * 0.072)
    caption_size = int(W * 0.052)

    plan = plan_captions(script, duration)
    print(f"💬 자막 카드 {len(plan)}장 (총 {duration:.1f}초)")

    # 1) 제목 카드 (화면 위쪽 고정)
    title_card = make_text_card(title, title_size, 'yellow', TITLE_FONT, size)
    title_y = int(H * 0.05)
    title_bottom = title_y + title_card.h

    # 2) 자막 카드는 아랫변을 맞춰 고정 (카드 높이가 달라도 흔들리지 않음)
    cards = [make_text_card(text, caption_size, 'white', CAPTION_FONT, size) for text, _, _ in plan]
    cap_bottom = int(H * CAPTION_BOTTOM)
    tallest = max((c.h for c in cards), default=0)

    # 3) 두 글자 덩어리 사이의 빈 영역 = 블로그 이미지가 들어갈 자리
    band_top = title_bottom + int(H * 0.02)
    band_bottom = (cap_bottom - tallest) - int(H * 0.02)
    band = (band_top, band_bottom)
    print(f"🧭 이미지 영역: {band_top} ~ {band_bottom} (높이 {band_bottom - band_top}px)")

    bg = build_background(title, script, plan, duration, size, bg_keyword,
                          image_folder_id=image_folder_id, band=band)

    title_clip = title_card.set_position(('center', title_y)).set_duration(duration)

    caption_clips = []
    for card, (text, start, seg) in zip(cards, plan):
        y = cap_bottom - card.h
        y = max(y, title_bottom + int(H * 0.02))          # 제목과 겹치지 않게
        y = min(y, H - card.h - int(H * 0.12))            # 워터마크 자리 확보
        caption_clips.append(
            card.set_position(('center', y)).set_start(start).set_duration(seg)
        )

    layers = [bg, title_clip] + caption_clips
    if WATERMARK:
        wm = make_watermark_clip(WATERMARK, size)
        wm = wm.set_position(('center', int(H * 0.915) - wm.h // 2)).set_duration(duration)
        layers.append(wm)

    video = CompositeVideoClip(layers, size=size)
    video = video.set_audio(audio_clip).set_duration(duration)
    video.write_videofile(output_path, fps=24, codec='libx264',
                          audio_codec='aac', preset='veryfast', threads=4)
    print(f"✅ 영상 렌더링 완료: {output_path}")
    return output_path


if __name__ == "__main__":
    title = clean_script(os.environ.get('TITLE', '기본 쇼츠 제목입니다'))
    script = clean_script(os.environ.get('SCRIPT', '여기에 쇼츠 스크립트 내용이 들어갑니다.'))
    drive_folder_id = os.environ.get('DRIVE_FOLDER_ID')
    image_folder_id = os.environ.get('IMAGE_FOLDER_ID', '').strip()
    bg_keyword = os.environ.get('BG_KEYWORD', '')
    row = os.environ.get('ROW', '')
    description = os.environ.get('DESCRIPTION', '')
    tags_text = os.environ.get('TAGS', '')

    print(f"📌 타이틀: {title}")
    if image_folder_id:
        print(f"🗂️ 블로그 이미지 폴더: {image_folder_id}")
    else:
        print("🗂️ 블로그 이미지 폴더가 없어 Pixabay 사진을 씁니다.")
    if bg_keyword:
        print(f"🔑 제미나이 배경 검색어: {bg_keyword}")
    if row:
        print(f"📄 시트 {row}행")

    output_file = "output_shorts.mp4"
    drive_name = make_output_name(title)

    try:
        audio_file = generate_audio(script)
        render_video(title, script, audio_file, output_file,
                     bg_keyword=bg_keyword, image_folder_id=image_folder_id)

        drive_link = ""
        if drive_folder_id and os.path.exists(output_file):
            drive_link = upload_to_google_drive(output_file, drive_folder_id, drive_name) or ""
        else:
            print("⚠️ DRIVE_FOLDER_ID가 없거나 파일이 없어 드라이브 업로드를 생략합니다.")

        # 유튜브 업로드는 실패해도 전체를 중단하지 않는다
        youtube_link = upload_to_youtube(output_file, title, description, tags_text)

        # 인스타그램 API용 공개 URL (GitHub 릴리스). 실패해도 전체를 중단하지 않는다
        public_video_url = ""
        if os.path.exists(output_file):
            release_tag = f"shorts-{row or 'r'}-{datetime.now(timezone(timedelta(hours=9))).strftime('%Y%m%d%H%M%S')}"
            public_video_url = upload_to_github_release(output_file, release_tag, title)

        # 인스타그램 릴스 발행 — Make 발행 허브 경유 방식 사용 (2026-09-04부터).
        # 기존 방식(publish_to_instagram, Meta API 직접 호출)은 0단계(Meta 개발자 앱 등록) 버그로
        # 막혀 있어 지금은 호출하지 않음 — 함수 자체는 지우지 않고 그대로 남겨둠.
        # 나중에 0단계가 풀려서 직접 호출로 되돌리고 싶으면, 아래 두 줄을 다음으로 바꾸면 됨:
        #   instagram_result = publish_to_instagram(public_video_url, ig_caption)
        #   if instagram_result: print(f"📸 인스타그램 결과: {instagram_result}")
        ig_caption = (description or title).strip()
        publish_via_make_webhook(public_video_url, ig_caption)

        send_callback(row, "완료", drive_link, drive_name, youtube_link, public_video_url)

    except Exception as err:
        print(f"❌ 작업 실패: {err}")
        send_callback(row, "실패: " + str(err)[:120], "", "", "")
        raise
