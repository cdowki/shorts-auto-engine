import os
import sys
import urllib.parse
import requests
from moviepy.config import change_settings

# 환경변수 로드
TITLE = os.environ.get("TITLE", "테스트 쇼츠 제목")
SCRIPT = os.environ.get("SCRIPT", "테스트용 쇼츠 본문 대본 내용입니다.")
AUDIO_URL = os.environ.get("AUDIO_URL", "")

def encodeURIComponent_py(text):
    return urllib.parse.quote(text)

def main():
    print("=== 쇼츠 자동 렌더링 프로세스 시작 ===")
    
    # 1. 오디오(TTS) 다운로드 및 검증
    print("1. 오디오(TTS) 생성 및 다운로드 중...")
    if AUDIO_URL:
        tts_url = AUDIO_URL
    else:
        encoded_text = encodeURIComponent_py(SCRIPT)
        tts_url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={encoded_text}&tl=ko&client=tw-ob"
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    res = requests.get(tts_url, headers=headers)
    
    audio_file = "voice.mp3"
    with open(audio_file, "wb") as f:
        f.write(res.content)
        
    # 다운로드된 오디오 파일 검증 (0바이트이거나 비정상일 경우 예외 처리)
    if not os.path.exists(audio_file) or os.path.getsize(audio_file) < 100:
        print(f"❌ 에러: 오디오 파일 다운로드 실패 (크기: {os.path.getsize(audio_file) if os.path.exists(audio_file) else 0}바이트)")
        sys.exit(1)
        
    print("✅ 오디오 다운로드 및 검증 완료")

    # MoviePy 임포트 (ImageMagick 경로 설정 포함)
    from moviepy.editor import AudioFileClip, ColorClip, TextClip, CompositeVideoClip
    
    audio_clip = AudioFileClip(audio_file)
    duration = min(audio_clip.duration, 59)

    # 2. 9:16 세로형 배경 생성 (1080x1920)
    print("2. 영상 배경 및 자막 합성 중...")
    bg_clip = ColorClip(size=(1080, 1920), color=(15, 23, 42), duration=duration)
    
    # 3. 제목 자막 (나눔고딕 또는 시스템 기본 폰트 사용)
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
    
    # 4. 본문 자막
    body_clip = TextClip(
        SCRIPT,
        fontsize=42,
        color='white',
        font=font_name,
        size=(900, None),
        method='caption',
        align='center'
    ).set_position(('center', 'center')).set_duration(duration)
    
    # 5. 최종 렌더링
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

if __name__ == "__main__":
    main()
