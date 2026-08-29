import os, requests
from moviepy.editor import AudioFileClip, ColorClip, TextClip, CompositeVideoClip

def build_shorts():
    title = os.environ.get("TITLE", "쇼츠_영상")
    script = os.environ.get("SCRIPT", "")
    audio_url = os.environ.get("AUDIO_URL", "")
    
    if audio_url:
        res = requests.get(audio_url)
        with open("voice.mp3", "wb") as f:
            f.write(res.content)
            
    audio_clip = AudioFileClip("voice.mp3")
    duration = audio_clip.duration
    video_bg = ColorClip(size=(1080, 1920), color=(20, 24, 30), duration=duration)
    
    title_text = TextClip(title, fontsize=48, color='yellow', font='NanumGothic-Bold', size=(960, None), method='caption').set_position(('center', 250)).set_duration(duration)
    clean_script = script.replace(". ", ".\n").replace("! ", "!\n").replace("? ", "?\n")
    body_text = TextClip(clean_script, fontsize=44, color='white', font='NanumGothic-Bold', size=(920, None), method='caption', align='center').set_position(('center', 'center')).set_duration(duration)
    
    final = CompositeVideoClip([video_bg, title_text, body_text]).set_audio(audio_clip)
    final.write_videofile("output_shorts.mp4", fps=24, codec="libx264", audio_codec="aac", preset="ultrafast")

if __name__ == "__main__":
    build_shorts()
