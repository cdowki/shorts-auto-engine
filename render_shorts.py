import os
import io
import json
import re
import requests
from gtts import gTTS
from moviepy.editor import TextClip, AudioFileClip, ColorClip, CompositeVideoClip
from googleapiclient.discovery import build
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


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


def render_video(title, script, audio_path, output_path="output_shorts.mp4"):
    print("🎬 쇼츠 영상 렌더링 시작...")

    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration

    bg_clip = ColorClip(size=(1080, 1920), color=(20, 20, 20), duration=duration)

    title_clip = TextClip(
        title,
        fontsize=60,
        color='white',
        font='NanumGothic',
        size=(900, None),
        method='caption'
    ).set_position(('center', 300)).set_duration(duration)

    script_clip = TextClip(
        script,
        fontsize=45,
        color='yellow',
        font='NanumGothic',
        size=(900, None),
        method='caption'
    ).set_position(('center', 600)).set_duration(duration)

    video = CompositeVideoClip([bg_clip, title_clip, script_clip])
    video = video.set_audio(audio_clip)

    video.write_videofile(
        output_path,
        fps=24,
        codec='libx264',
        audio_codec='aac',
        preset='fast'
    )
    print(f"✅ 영상 렌더링 완료: {output_path}")
    return output_path


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

        file_id = file.get('id')
        print(f"✅ 영상 드라이브 업로드 성공! 파일 ID: {file_id}")
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
                file_id = file_id_match.group(1)
                download_audio_via_api(file_id, audio_file)
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
