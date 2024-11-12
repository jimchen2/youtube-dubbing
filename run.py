from utils import *

def process_video(video_url, target_lang='ru'):
    """Main processing function"""
    # Initialize database
    db_path = init_db()
    
    # Step 1: Check if video exists in KV store
    existing_s3_url = check_kv_store(db_path, video_url)
    if existing_s3_url:
        return existing_s3_url

    try:
        # Step 2: Download audio
        audio_path = download_audio(video_url)

        # Step 3: Detect language
        detected_lang = detect_audio_language(audio_path)
        if detected_lang == target_lang or detected_lang is None:
            return None  # No need to dub

        # Step 4: Get diarization and transcription
        diarization = get_diarization(audio_path)
        segments = transcribe_segments(audio_path, diarization)

        # Step 5: Translate segments
        translated_segments = translate(detected_lang, target_lang, segments)

        # Step 6: Generate TTS
        generate_tts_silero(translated_segments, target_lang)

        # Step 7: Upload to S3
        output_path = "output_audio.wav"
        s3_url = upload_to_s3(output_path)

        # Step 8: Update KV store
        if not update_kv_store(db_path, video_url, s3_url):
            raise Exception("Failed to update KV store")

        # Step 9: Return S3 URL
        return s3_url

    except Exception as e:
        print(f"Error processing video: {e}")
        return None
    finally:
        # Step 10: Clean up
        cleanup_temp_files()

if __name__ == "__main__":
    video_url = "https://www.youtube.com/shorts/vd9GxG5Qn-k/"
    result = process_video(video_url, target_lang='ru')
    print(f"Processed audio URL: {result}")
