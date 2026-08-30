import os
import sys
import urllib.parse
from moviepy.config import change_settings

# 환경변수 로드
TITLE = os.environ.get("TITLE", "테스트 쇼츠 제목")
SCRIPT = os.environ.get("SCRIPT", "테스트용 쇼츠 본문 대본 내용입니다.")
AUDIO_URL = os.environ.get("AUDIO_URL", "")

def main():
    print("=== 쇼츠 자동 렌더링 프로세스 시작 ===")
    
    audio_file = "voice.mp3"
    
    # 1. 오디오(TTS) 생성 (gTTS 라이브러리 사용으로 안정성 확보)
    print("1. 오디오(TTS) 생성 중...")
    try:
        from gtts import gTTS
        tts = gTTS(text=SCRIPT, lang='ko')
        tts.save(audio_file)
    except Exception as e:
        print(f"❌ gTTS 생성 실패, 대체 방식을 시도합니다: {e}")
        # gTTS 실패 시 빈 오디오 혹은 기본 처리
        sys.exit(1)
        
    # 파일 검증
    if not os.path.exists(audio_file) or os.path.getsize(audio_file) < 500:
        print(f"❌ 에러: 생성된 오디오 파일이 손상되었거나 비어있습니다.")
        sys.exit(1)
        
    print("✅ 오디오 생성 및 검증 완료")

    # MoviePy 임포트 및 렌더링
    from moviepy.editor import AudioFileClip, ColorClip, TextClip, CompositeVideoClip
    
    audio_clip = AudioFileClip(audio_file)
    duration = min(audio_clip.duration, 59)

    # 2. 9:16 세로형 배경 생성 (1080x1920)
    print("2. 영상 배경 및 자막 합성 중...")
    bg_clip = ColorClip(size=(1080, 1920), color=(15, 23, 42), duration=duration)
    
    # 3. 폰트 설정
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
    
    # 4. 최종 렌더링
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
