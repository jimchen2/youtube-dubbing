## Client(TODO)

1. User triggers extension on a webpage
   Exceptions: The uzcrl must match a fixed pattern (else, throw an error), like `youtube.com/watch?...`
2. Submit Url to Remote Server, as well as target language
   Exceptions: The remote server is reachable (else, throw an error, can't reach server)
3. Server returns S3 url
4. Start playing the audio track from S3, so like if the video is at 4:00, start playing at 4:00 audio track from S3.

## Remote Server

Note: `python3.8` works, `python3.13` doesn't work with the `openai-whisper`

1. See if video url is in KV Store(basically video-url to s3-url)

- If it is, return the s3 audio url
- If it isn't, continue

2. Use `yt-dlp` to download audio from video
   Exceptions: Cannot download video, return error
3. Use Whisper to determine the language spoken

- If video language == target language, or video language is NA, there is no point in dubbing, return
- Else, continue

4. Use Speaker diarization + Openai Whisper
   Exceptions: Cannot Run diarization and Whisper on audio, return error
   Format be like this

- second 1-3, speaker 1, "Hello Everybody"
- second 5-9, speaker 2, "Today we are going to introduce"
- second 10-14, speaker 1(again), "The news is"

5. Translate the languages into target language like this with Helsinki-NLP, return like this

- second 1-3, speaker 1, "Привет всем"
- second 5-9, speaker 2, "Сегодня мы познакомим вас с"
- second 10-14, speaker 1(again), "Новость такова"

6. Text to speech with different speakers
   Make sure the generated audio track is the same length as original audio, if not, pad with silence.
7. Send the audio track to S3
8. Put the S3 object ID into KV Store
9. Return the S3 audio track url to client
10. Clean Up



```
root@localhost:~/youtube-dubbing/server# curl -X POST \
  http://127.0.0.1/process-video \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: 1' \
  -d '{
    "video_url": "https://1a-1791.com/video/cwg9/s8/2/u/4/H/y/u4Hyt.caa.mp4?u=0&b=0",
    "target_lang": "ru"
}'
{"s3_url":"https://pub-c83792778c14423db6c2289e5a4e6a79.r2.dev/audio/89098f83-2ad9-486f-a505-ad73db8cb0ce.wav","status":"success"}
```

A second request yield the same results, but it's instant(much faster).