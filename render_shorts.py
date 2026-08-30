import os
import sys
import urllib.parse
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# 환경변수 로드
TITLE = os.environ.get("TITLE", "테스트 쇼츠 제목")
SCRIPT = os.environ.get("SCRIPT", "테스트용 쇼츠 본문 대본 내용입니다.")
AUDIO_URL = os.environ.get("AUDIO_URL", "")
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "")

def upload_to_google_drive(file_path, file_name, folder_id):
    """렌더링된 MP4 파일을 구글 드라이브로 업로드하고 공유 링크를 생성합니다."""
    print("3. 구글 드라이브 업로드 중...")
    try:
        # GitHub Secrets 등에 저장된 서비스 계정 JSON 환경변수 활용 또는 기본 인증
        # (환경변수 GOOGLE_SERVICE_ACCOUNT_JSON 이 설정되어 있거나 기본 권한 사용)
        creds = None
        if "GOOGLE_SERVICE_ACCOUNT_KEY" in os.environ:
            import json
            service_account_info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_KEY"])
            creds = service_account.Credentials.from_service_account_info(
                service_account_info, scopes=['https://www.googleapis.com/auth/drive']
            )
        else:
            # 로컬 또는 기본 인증 환경
            creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/drive'])

        service = build('drive', 'v3', credentials=creds)

        file_metadata = {
            'name': file_name,
            'parents': [folder_id] if folder_id else []
        }
        media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True)
        
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink'
        ).execute()

        file_id = file.get('id')
        web_link = file.get('webViewLink')
        print(f"✅ 구글 드라이브 업로드 성공!")
        print(f" - 파일 ID: {file_id}")
        print(f" - 공유 링크: {web_link}")
        return file_id

    except Exception as e:
        print(f"⚠️ 구글 드라이브 업로드 중 오류 발생 (아티팩트는 정상 보관됨): {e}")
        return None

def main():
    print("=== 쇼츠 자동 렌더링 및 업로드 프로세스 시작 ===")
    
    audio_file = "voice.mp3"
    
    # 1. 오디오(TTS) 생성 (gTTS 라이브러리 사용)
    print("1. 오디오(TTS) 생성 중...")
    try:
        from gtts import gTTS
        tts = gTTS(text=SCRIPT, lang='ko')
        tts.save(audio_file)
    except Exception as e:
        print(f"❌ gTTS 생성 실패: {e}")
        sys.exit(1)
        
    if not os.path.exists(audio_file) or os.path.getsize(audio_file) < 500:
        print(f"❌ 에러: 생성된 오디오 파일이 손상되었거나 비어있습니다.")
        sys.exit(1)
        
    print("✅ 오디오 생성 및 검증 완료")

    # MoviePy 임포트 및 렌더링
    from moviepy.editor import AudioFileClip, ColorClip, TextClip, CompositeVideoClip
    
    audio_clip = AudioFileClip(audio_file)
    duration = min(audio_clip.duration, 59)

    # 2. 9:16 세로형 배경 및 자막 합성 (1080x1920)
    print("2. 영상 배경 및 자막 합성 중...")
    bg_clip = ColorClip(size=(1080, 1920), color=(15, 23, 42), duration=duration)
    
    font_name = "NanumGothic" if os.path.exists("/usr/share/fonts/truetype/nanum/NanumGothic.ttf") else "Arial"
    
    title_clip = TextClip(
        TITLE,
        fontsize=50,
        color='yellow',
        font=font_name,
        size=(940, None),
        method='caption',
        align='center'
    ).set_position(('center', 260)).set_duration(duration)
    
    body_clip = TextClip(
        SCRIPT,
        fontsize=42,
        color='white',
        font=font_name,
        size=(900, None),
        method='caption',
        align='center'
    ).set_position(('center', 'center')).set_duration(duration)
    
    output_filename = "output_shorts.mp4"
    final_video = CompositeVideoClip([bg_clip, title_clip, body_clip]).set_audio(audio_clip)
    
    final_video.write_videofile(
        output_filename,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast"
    )
    print(f"🎉 렌더링 성공! 파일명: {output_filename}")

    # 3. 구글 드라이브 업로드 실행
    if DRIVE_FOLDER_ID:
        upload_to_google_drive(output_filename, f"{TITLE}.mp4", DRIVE_FOLDER_ID)
    else:
        print("ℹ️ DRIVE_FOLDER_ID가 지정되지 않아 드라이브 업로드를 생략합니다.")

if __name__ == "__main__":
    main()
