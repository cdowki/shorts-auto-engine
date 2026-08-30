import os
import json
import requests
from gtts import gTTS
from moviepy.editor import TextClip, AudioFileClip, ColorClip, CompositeVideoClip
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaFileUpload

def generate_audio(script_text, output_path="audio.mp3"):
    """텍스트를 gTTS를 이용해 음성 파일로 변환"""
    print("🔊 음성(TTS) 생성 중...")
    tts = gTTS(text=script_text, lang='ko')
    tts.save(output_path)
    return output_path

def render_video(title, script, audio_path, output_path="output_shorts.mp4"):
    """MoviePy를 이용한 쇼츠 영상 렌더링"""
    print("🎬 쇼츠 영상 렌더링 시작...")
    
    # 1. 오디오 로드 및 길이 측정
    audio_clip = AudioFileClip(audio_path)
    duration = audio_clip.duration
    
    # 2. 배경 클립 생성 (9:16 세로형 규격: 1080x1920)
    bg_clip = ColorClip(size=(1080, 1920), color=(20, 20, 20), duration=duration)
    
    # 3. 타이틀 및 스크립트 텍스트 클립 생성
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
    
    # 4. 컴포지트 비디오 합성
    video = CompositeVideoClip([bg_clip, title_clip, script_clip])
    video = video.set_audio(audio_clip)
    
    # 5. 파일 내보내기
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
    """구글 드라이브 업로드 및 서비스 계정 스토리지 쿼터 제한 우회 처리"""
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
        # supportsAllDrives=True 옵션 추가로 공유 폴더/드라이브 호환성 확보
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
        
        file_id = file.get('id')
        print(f"✅ 구글 드라이브 업로드 성공! 파일 ID: {file_id}")
        
        # 개인 계정(cdowki@gmail.com) 소유권 이전 시도 (스토리지 쿼터 초과 에러 방지)
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
            print(f"⚠️ 소유권 이전 경고 (권한 설정에 따라 무시 가능): {perm_error}")

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
    if audio_url:
        print(f"📥 오디오 다운로드 중: {audio_url}")
        res = requests.get(audio_url)
        with open(audio_file, 'wb') as f:
            f.write(res.content)
    else:
        generate_audio(script, audio_file)
        
    output_file = "output_shorts.mp4"
    render_video(title, script, audio_file, output_file)
    
    if drive_folder_id and os.path.exists(output_file):
        upload_to_google_drive(output_file, drive_folder_id)
    else:
        print("⚠️ DRIVE_FOLDER_ID가 설정되지 않았거나 렌더링된 파일이 없어 드라이브 업로드를 건너뜁니다.")
