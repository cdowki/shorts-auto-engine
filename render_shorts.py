import os
import json
import requests
from gtts import gTTS
from moviepy.editor import TextClip, AudioFileClip, ColorClip, CompositeVideoClip
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload

def generate_audio(script_text, output_path="audio.mp3"):
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
    print("☁️ 구글 드라이브 업로드 중...")
    SCOPES = ['https://www.googleapis.com/auth/drive']
    
    creds_json = os.environ.get('GOOGLE_SERVICE_ACCOUNT_JSON')
    if not creds_json:
        raise ValueError("❌ GOOGLE_SERVICE_ACCOUNT_JSON 환경 변수가 설정되지 않았습니다.")
    
    creds_info = json.loads(creds_json)
    credentials = service_account.Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    service = build('drive', 'v3', credentials=credentials)

    file_metadata = {
        'name': os.path.basename(file_path),
        'parents': [folder_id]
    }
    
    media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True)

    try:
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
        
        file_id = file.get('id')
        print(f"✅ 구글 드라이브 업로드 성공! 파일 ID: {file_id}")
        
        try:
            permission = {
                'type': 'user',
                'role': 'owner',
                'emailAddress': 'cdowki@gmail.com'
            }
            service.permissions().create(
                fileId=file_id,
                body=permission,
                transferOwnership=True,
                sendNotificationEmail=False,
                supportsAllDrives=True
            ).execute()
            print("👤 파일 소유권이 개인 계정(cdowki@gmail.com)으로 성공적으로 이전되었습니다.")
        except Exception as perm_error:
            print(f"⚠️ 소유권 이전 경고: {perm_error}")

        return file.get('webViewLink')

    except Exception as e:
        print(f"❌ 구글 드라이브 업로드 중 오류 발생: {e}")
        raise e

if __name__ == "__main__":
    title = os.environ.get('TITLE', '기본 쇼츠 제목입니다')
    script = os.environ.get('SCRIPT', '여기에 쇼츠 스크립트 내용이 들어갑니다.')
    audio_url = os.environ.get('AUDIO_URL', '')
    drive_folder_id = os.environ.get('DRIVE_FOLDER_ID')
    
    print(f"📌 타이틀: {title}")
    
    audio_file = "temp_audio.mp3"
    
    # 구글 드라이브 링크 완벽 정제 및 직접 다운로드 주소 변환 (HTML 에러 방지)
    if audio_url and "drive.google.com" in audio_url:
        import re
        file_id_match = re.search(r'/d/([a-zA-Z0-9_-]+)', audio_url) or re.search(r'id=([a-zA-Z0-9_-]+)', audio_url)
        if file_id_match:
            file_id = file_id_match.group(1)
            audio_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm=t"
            print(f"🔄 구글 드라이브 파일 ID({file_id}) 추출 완료 -> 안전 다운로드 링크로 전환")

    if audio_url:
        print(f"📥 오디오 다운로드 시도 중: {audio_url}")
        response = requests.get(audio_url, stream=True)
        
        # HTML 에러 페이지가 내려왔는지 검증
        if "text/html" in response.headers.get("Content-Type", ""):
            raise ValueError("❌ 오디오 다운로드 실패: 구글 드라이브 권한이 '링크가 있는 모든 사용자(뷰어)'로 열려있지 않거나 잘못된 링크입니다.")
            
        with open(audio_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        print(f"✅ 오디오 파일 다운로드 완료 (크기: {os.path.getsize(audio_file)} 바이트)")
    else:
        print("🔊 오디오 URL이 없어 gTTS로 대체 음성을 생성합니다.")
        generate_audio(script, audio_file)
        
    output_file = "output_shorts.mp4"
    render_video(title, script, audio_file, output_file)
    
    if drive_folder_id and os.path.exists(output_file):
        upload_to_google_drive(output_file, drive_folder_id)
    else:
        print("⚠️ DRIVE_FOLDER_ID가 설정되지 않았거나 렌더링된 파일이 없어 업로드를 건너뜁니다.")
