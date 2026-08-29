import os, base64, requests
from moviepy.editor import AudioFileClip, ColorClip, TextClip, CompositeVideoClip

def build_and_upload_shorts():
    title = os.environ.get("TITLE", "쇼츠_영상")
    script = os.environ.get("SCRIPT", "")
    audio_url = os.environ.get("AUDIO_URL", "")
    folder_id = os.environ.get("DRIVE_FOLDER_ID", "1PC7nRbvu8lcjpE13FXY97ZwV2Z2VuBkn")
    webhook_url = os.environ.get("WEBHOOK_URL", "")
    
    # 1. 오디오 다운로드
    if audio_url:
        res = requests.get(audio_url)
        with open("voice.mp3", "wb") as f:
            f.write(res.content)
            
    audio_clip = AudioFileClip("voice.mp3")
    duration = min(audio_clip.duration, 59) # 60초 미만 쇼츠 규격
    
    # 2. 9:16 비디오 배경 및 텍스트 합성
    video_bg = ColorClip(size=(1080, 1920), color=(15, 23, 42), duration=duration)
    
    title_text = TextClip(title, fontsize=46, color='yellow', font='NanumGothic-Bold', size=(940, None), method='caption').set_position(('center', 260)).set_duration(duration)
    
    clean_script = script.replace(". ", ".\n").replace("! ", "!\n").replace("? ", "?\n")
    body_text = TextClip(clean_script, fontsize=42, color='white', font='NanumGothic-Bold', size=(900, None), method='caption', align='center').set_position(('center', 'center')).set_duration(duration)
    
    output_filename = "output_shorts.mp4"
    final = CompositeVideoClip([video_bg, title_text, body_text]).set_audio(audio_clip)
    final.write_videofile(output_filename, fps=24, codec="libx264", audio_codec="aac", preset="ultrafast")
    
    # 3. 구글 드라이브 웹훅 자동 전송
    if webhook_url and os.path.exists(output_filename):
        with open(output_filename, "rb") as video_file:
            video_base64 = base64.b64encode(video_file.read()).decode('utf-8')
            
        payload = {
            "title": title,
            "folder_id": folder_id,
            "video_base64": video_base64
        }
        res = requests.post(webhook_url, json=payload)
        print("드라이브 업로드 응답:", res.text)

if __name__ == "__main__":
    build_and_upload_shorts()
