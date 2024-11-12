from transformers import AutoProcessor, AutoModel
import torch
import numpy as np
import scipy.io.wavfile as wavfile
import yt_dlp
import whisper
import torch
from pyannote.audio import Pipeline
import soundfile as sf
from transformers import VitsModel, AutoTokenizer
import os
from transformers import MarianMTModel, MarianTokenizer
import sqlite3
from pathlib import Path
import uuid


from dotenv import load_dotenv

# Load environment variables
load_dotenv()


import boto3
import os

def download_audio(video_url):
    """Download audio from YouTube video."""
    try:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '192',
            }],
            'outtmpl': 'temp_audio.%(ext)s'
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])

        return "temp_audio.wav"
    except Exception as e:
        raise Exception(f"Failed to download video: {str(e)}")
    

def detect_audio_language(audio_file_path, model_size="base"):
    try:
        model = whisper.load_model(model_size)
        audio = whisper.load_audio(audio_file_path)
        audio = whisper.pad_or_trim(audio)
        mel = whisper.log_mel_spectrogram(audio).to(model.device)
        _, probs = model.detect_language(mel)
        detected_language = max(probs, key=probs.get)
        print(detected_language)
        return detected_language
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return None
    

def get_diarization(audio_path):
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1").to(device)
    return pipeline(audio_path)

def transcribe_segments(audio_path, diarization):
    model = whisper.load_model("base")
    results = []

    # Load the audio file
    audio, sr = sf.read(audio_path)

    for segment, track, speaker in diarization.itertracks(yield_label=True):
        start_sample = int(segment.start * sr)
        end_sample = int(segment.end * sr)

        segment_audio = audio[start_sample:end_sample]
        sf.write("temp_segment.wav", segment_audio, sr)
        result = model.transcribe("temp_segment.wav")
        transcript = result["text"].strip()

        results.append({
            'start': segment.start,
            'end': segment.end,
            'speaker': speaker,
            'text': transcript
        })

    print(results)

    return results



def translate(source_lang, target_lang, segments):
    try:
        model_name = f"Helsinki-NLP/opus-mt-{source_lang}-{target_lang}"

        # Load model and tokenizer
        tokenizer = MarianTokenizer.from_pretrained(model_name)
        model = MarianMTModel.from_pretrained(model_name)

        # Translate each segment
        translated_segments = []
        for segment in segments:
            translated_segment = segment.copy()
            inputs = tokenizer(segment['text'], return_tensors="pt", padding=True)
            translated = model.generate(**inputs)
            translated_text = tokenizer.decode(translated[0], skip_special_tokens=True)
            translated_segment['text'] = translated_text
            translated_segments.append(translated_segment)

        print(translated_segments)

        return translated_segments

    except Exception as e:
        return f"Translation error: {str(e)}"
    

def generate_tts_silero(translated_segments, target_lang):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(4)

    # Download and load the model
    local_file = 'model.pt'

    if not os.path.isfile(local_file):
        torch.hub.download_url_to_file('https://models.silero.ai/models/tts/ru/v4_ru.pt',
                                      local_file)

    model = torch.package.PackageImporter(local_file).load_pickle("tts_models", "model")
    model.to(device)

    # Available Russian speakers in v4_ru model
    speakers = {
        "SPEAKER_00": "aidar",      # male voice
        "SPEAKER_01": "baya",       # female voice
        "SPEAKER_02": "kseniya",    # female voice
        "SPEAKER_03": "xenia",      # female voice
        "SPEAKER_04": "eugene",     # male voice
        "DEFAULT": "xenia"
    }

    audio_segments = []
    for segment in translated_segments:
        text = segment['text']
        if not text.strip():
            continue

        speaker = speakers.get(segment.get('speaker', 'DEFAULT'), speakers['DEFAULT'])

        audio = model.apply_tts(text=text,
                               speaker=speaker,
                               sample_rate=48000)

        audio_numpy = audio.cpu().numpy()
        desired_length = int(segment['end'] - segment['start']) * 48000

        if len(audio_numpy) > desired_length:
            audio_numpy = audio_numpy[:desired_length]
        else:
            padding = np.zeros(desired_length - len(audio_numpy))
            audio_numpy = np.concatenate([audio_numpy, padding])

        audio_segments.append(audio_numpy)

    final_audio = np.concatenate(audio_segments)
    sf.write("output_audio.wav", final_audio, samplerate=48000)





def init_db():
    """Initialize SQLite database"""
    data_dir = Path("data")
    data_dir.mkdir(exist_ok=True)
    db_path = data_dir / "video_audio_mapping.db"
    
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS video_audio_mapping (
                video_url TEXT PRIMARY KEY,
                s3_url TEXT NOT NULL
            )
        """)
        conn.commit()
    return db_path

def check_kv_store(db_path, video_url):
    """Check if video URL exists in local store"""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT s3_url FROM video_audio_mapping WHERE video_url = ?", 
                (video_url,)
            )
            result = cursor.fetchone()
            if result:
                return result[0]
        return None
    except sqlite3.Error as e:
        print(f"Error checking local store: {e}")
        return None

def upload_to_s3(file_path):
    """Upload file to S3"""
    try:
        bucket_name = os.getenv('S3_BUCKET_NAME')
        endpoint_url = os.getenv('S3_ENDPOINT_URL')  # Add this line to get endpoint URL from env
        
        s3 = boto3.client(
            's3',
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_DEFAULT_REGION'),
            endpoint_url=endpoint_url  # Add the endpoint_url parameter
        )
        
        # Generate unique filename with original extension
        original_extension = Path(file_path).suffix
        unique_filename = f"{uuid.uuid4()}{original_extension}"
        s3_key = f"audio/{unique_filename}"
        
        s3.upload_file(file_path, bucket_name, s3_key)
        
        base_url = os.getenv('S3_BASE_URL')
        s3_url = f"{base_url}/{s3_key}"
        return s3_url
    except Exception as e:
        print(f"Error uploading to S3: {e}")
        return None

    
def update_kv_store(db_path, video_url, s3_url):
    """Update local store with mapping"""
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO video_audio_mapping (video_url, s3_url) VALUES (?, ?)",
                (video_url, s3_url)
            )
            conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"Error updating local store: {e}")
        return False

def cleanup_temp_files():
    """Clean up temporary files"""
    temp_files = ["temp_audio.wav", "output_audio.wav", "temp_segment.wav"]
    for temp_file in temp_files:
        if os.path.exists(temp_file):
            os.remove(temp_file)