# -*- coding: utf-8 -*-
import os
import whisper
import asyncio
import edge_tts
from moviepy.editor import VideoFileClip, CompositeAudioClip, AudioFileClip
from datetime import datetime
import traceback
from googletrans import Translator, LANGUAGES
import time

# Thiết lập thời gian hiện tại cho tên tệp
current_datetime = datetime.now()
formatted_datetime = current_datetime.strftime("%d-%m-%Y-%H-%M")


# Khởi tạo mô hình Whisper
model = whisper.load_model("base")


def wait_for_file(file_path, timeout=10):
    start_time = time.time()
    while time.time() - start_time < timeout:
        if os.path.exists(file_path):
            return True
        time.sleep(0.1)
    return False


# Bước 1: Trích xuất âm thanh từ video
def extract_audio(video_path, audio_path):
    try:
        video = VideoFileClip(video_path)
        audio = video.audio
        audio.write_audiofile(audio_path)
        print(f"Đã trích xuất âm thanh từ video: {audio_path}")
        return True
    except Exception as e:
        print(f"Không thể trích xuất âm thanh từ video: {e}")
        return False


def translate_text(text, src_lang="zh-cn", dest_lang="vi"):
    print(f"Đang dịch văn bản....")
    try:
        translator = Translator()
        translated = translator.translate(text, src=src_lang, dest=dest_lang)
        result = translated.text
        return result
    except Exception as e:
        print(f"Đã xảy ra lỗi khi dịch văn bản: {traceback.format_exc()}")
        return text  # Trả về văn bản gốc nếu có lỗi


# Bước 2: Chuyển âm thanh thành văn bản với timestamps
def transcribe_audio(audio_path):
    try:
        print(f"Đang chuyển âm thanh thành văn bản từ file: {audio_path}")
        result = model.transcribe(
            audio_path, word_timestamps=True
        )  # Bật tính năng timestamps
        print(f"Kết quả nhận diện văn bản: {result['text']}")
        return result  # Trả về kết quả có timestamps
    except Exception as e:
        print(f"Không thể chuyển âm thanh thành văn bản: {e}")
        return None


# Bước 3: Chuyển văn bản thành giọng nói sử dụng Edge TTS
async def text_to_speech(
    text, output_audio_path, start_time=0, end_time=0, voice="vi-VN-NamMinhNeural"
):
    try:
        # Độ dài văn bản tính bằng số ký tự (chỉ tính các ký tự không phải khoảng trắng)
        text_length = len(text.replace(" ", ""))

        # Giả sử tốc độ đọc bình thường là 150 ký tự/phút
        normal_reading_rate = 165  # ký tự mỗi phút
        normal_reading_time_seconds = (
            text_length / normal_reading_rate
        ) * 60  # thời gian đọc bình thường (số giây)

        # Thời gian cần để đọc (tính theo giây)
        desired_time_seconds = end_time - start_time

        if desired_time_seconds > 0:
            # Tính tỷ lệ (rate) cần thiết để hoàn thành trong khoảng thời gian từ start_time đến end_time
            rate_percentage = (desired_time_seconds / normal_reading_time_seconds) * 100
            if rate_percentage > 0:
                rate = "+" + str(int(rate_percentage) + 15) + "%"
            else:
                rate = "-" + str(int(rate_percentage) + 15) + "%"
        else:
            rate = "0%"  # Nếu thời gian không hợp lệ, giữ tốc độ bình thường
        # print(f"Đang tạo giọng nói từ văn bản rate:{rate}, {text}")
        rate = "+40%"
        communicate = edge_tts.Communicate(text, rate=rate, voice=voice)
        await communicate.save(output_audio_path)
        # print(f"Đã tạo file giọng nói: {output_audio_path}")
        return output_audio_path
    except Exception as e:
        print(f"Lỗi khi tạo giọng nói: {traceback.format_exc()}")
        return None


arr_wait_remove = []


# Bước 4: Đồng bộ hóa và ghép giọng nói vào video với việc điều chỉnh thời gian bắt đầu
def sync_and_add_voice(video_path, transcription_result, output_path):
    try:
        print(f"Đang ghép giọng nói vào video...")

        # Lấy các timestamps từ kết quả nhận diện văn bản
        segments = transcription_result["segments"]

        # Tải video
        video = VideoFileClip(video_path)

        # Ghép các đoạn giọng nói vào video
        audio_clips = []
        process = 0

        for idx, segment in enumerate(segments):
            start_time = segment["start"]
            end_time = segment["end"]
            text = segment["text"]

            # Dịch từng đoạn văn bản
            translated_text = translate_text(text)
            # Tạo giọng nói cho từng đoạn văn bản dịch
            voice_path = os.path.join(
                os.getcwd(), "voice", f"voice_{start_time}_{end_time}.mp3"
            )
            asyncio.run(
                text_to_speech(translated_text, voice_path, start_time, end_time)
            )
            # Tải âm thanh đã tạo và cắt theo thời gian tương ứng
            voice = AudioFileClip(voice_path)
            segment_audio = voice.subclip(0, voice.duration)

            # Ghép đoạn giọng nói vào video tại thời gian bắt đầu của nó
            audio_clips.append(segment_audio.set_start(start_time))
            arr_wait_remove.append(voice_path)
            process += 1
            pecent = round((process / len(segments) * 100), 2)
            print(
                f"Đã xử lý: {pecent}%................................................................"
            )

        # Lấy âm thanh gốc từ video và giảm âm lượng (giảm 50%)
        original_audio = video.audio.volumex(0.1)

        # Ghép âm thanh gốc và âm thanh thuyết minh đã điều chỉnh
        final_audio = CompositeAudioClip([original_audio] + audio_clips)

        # Cập nhật video với âm thanh mới
        final_video = video.set_audio(final_audio)

        # Xuất video
        final_video.write_videofile(output_path, codec="libx264", audio_codec="aac")
        print(f"Đã tạo video hoàn chỉnh tại: {output_path}")
        return output_path
    except Exception as e:
        print(f"Lỗi khi ghép giọng nói vào video: {e}")
        return None


# Bước 5: Kết hợp toàn bộ các bước
def add_voiceover_to_video(video_path):
    try:
        # Đường dẫn file
        audio_path = os.path.join(os.getcwd(), "media", "audio_videoplayback.mp3")
        voice_path = os.path.join(
            os.getcwd(), "media", f"voice_{formatted_datetime}.mp3"
        )
        output_video_path = os.path.join(
            os.getcwd(),
            "media-output",
            f"video_with_voiceover_{formatted_datetime}.mp4",
        )

        # Bước 1: Trích xuất âm thanh
        if not extract_audio(video_path, audio_path):
            print("ERR: Not extract_audio")
            return

        # Bước 2: Chuyển âm thanh thành văn bản
        transcription_result = transcribe_audio(audio_path)
        if not transcription_result:
            print("ERR: Not transcription_result")
            return

        # Bước 3: Chuyển văn bản thành giọng nói
        # translated_text = transcription_result["text"]  # Giữ nguyên văn bản gốc
        # asyncio.run(text_to_speech(translate_text(translated_text), voice_path))

        # Bước 4: Ghép giọng nói vào video
        sync_and_add_voice(video_path, transcription_result, output_video_path)

        # Xóa các file tạm
        # os.remove(audio_path)
        # os.remove(voice_path)

        print(f"Quá trình hoàn tất! Video mới tại: {output_video_path}")
        for index, remove_path in enumerate(arr_wait_remove):
            os.remove(remove_path)
            print(f"{index}. Xóa voice audio path:{remove_path} thành công")

        # asyncio.run(os.remove(voice_path))
    except Exception as e:
        print(
            f"Đã xảy ra lỗi trong quá trình thêm thuyết minh: {traceback.format_exc()}"
        )


# Ví dụ sử dụng
video_file_path = "./media/videoplayback.mp4"
add_voiceover_to_video(video_file_path)
