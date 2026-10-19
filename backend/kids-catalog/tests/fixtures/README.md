# Generated audio fixtures

Self-generated 440 Hz sine tones, 0.15 seconds, mono 16 kHz. No third-party recordings. Metadata removed except encoder metadata emitted by FFmpeg.

```sh
ffmpeg -v error -f lavfi -i 'sine=frequency=440:duration=0.15' -map_metadata -1 -ac 1 -ar 16000 -y tone.mp3
ffmpeg -v error -f lavfi -i 'sine=frequency=440:duration=0.15' -map_metadata -1 -ac 1 -ar 16000 -y tone.m4a
```
