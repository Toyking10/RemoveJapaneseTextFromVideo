# Video Text Blur / Blackout (EasyOCR + OpenCV)

Blur or black out detected text in a video (e.g., hard-coded subtitles), then (optionally) mux the original audio back in using `ffmpeg`.

## What this does
- Reads an input video frame-by-frame
- Uses EasyOCR to detect text regions every N frames
- Either blurs or blacks out those regions
- Writes a processed video
- Attempts to copy the original audio into the output via `ffmpeg`

If `ffmpeg` is not available, the script will still produce a video, but it may have **no audio**.

---

## Requirements
- Python **3.10+** recommended
- `ffmpeg` available on your PATH (optional but strongly recommended)
- Enough disk space for temporary output files

### Install ffmpeg
**macOS (Homebrew)**
```bash
brew install ffmpeg
```

**Windows**
- Install ffmpeg and add it to your PATH (so `ffmpeg` works in PowerShell / CMD).
- Quick check:
```powershell
ffmpeg -version
```

**Ubuntu/Debian**
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

---

## Setup
Clone/download the repo, then create a virtual environment and install dependencies.

### macOS / Linux
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows (PowerShell)
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Note on first run:** EasyOCR may download model files the first time it runs. This can take a few minutes and requires internet access.

---

## Usage
Basic:
```bash
python blur_subs.py input.mp4 output.mp4
```

Blur mode (default):
```bash
python blur_subs.py input.mp4 output.mp4 --mode blur
```

Black bar mode:
```bash
python blur_subs.py input.mp4 output.mp4 --mode black
```

Speed vs accuracy:
```bash
# Detect text more frequently (slower but better at tracking changes)
python blur_subs.py input.mp4 output.mp4 --detect-every 5

# Detect text less frequently (faster but can miss short-lived text)
python blur_subs.py input.mp4 output.mp4 --detect-every 20
```

Reduce false positives (recommended starting point):
```bash
python blur_subs.py input.mp4 output.mp4 --conf-thresh 0.3
```

Try GPU (only if you know your environment supports it):
```bash
python blur_subs.py input.mp4 output.mp4 --gpu
```

---

## CLI options
- `input` (positional): Input video file path
- `output` (positional): Output video file path
- `--mode {blur,black}`: Blur region or fill with black (default: blur)
- `--detect-every N`: Run OCR detection every N frames and reuse boxes in between (default: 10)
- `--conf-thresh X`: Minimum OCR confidence to accept a detected text region (default: 0.0)
- `--gpu`: Use GPU for EasyOCR if available (default: CPU)
- `--band-ratio`: Currently unused (detection runs on the full frame)

---

## Output behavior
- The script writes a temporary file:
  - `<output>_video_only.<ext>`
- Then it tries to mux original audio back into the final `output` using `ffmpeg`.
- If muxing succeeds, the temporary “video only” file is removed.
- If muxing fails or `ffmpeg` is missing, it renames the video-only file to your requested `output`.

---

## Performance tips
- Start with:
  - `--detect-every 10`
  - `--conf-thresh 0.2` to `0.4`
- If you see the blur/black region “sticking” after text disappears:
  - That is partially handled already (boxes clear after a few empty detections), but tuning `--detect-every` can help.

---

## Troubleshooting

### “ffmpeg not found; leaving video without audio.”
Install ffmpeg and ensure it is on PATH.
- Check: `ffmpeg -version`

### Output video won’t play / codec issues
This script uses the `mp4v` codec via OpenCV’s `VideoWriter`. On some systems, codec support varies.
If playback fails, try:
- output as `.avi` (sometimes more compatible with `mp4v`), or
- install additional codecs, or
- re-encode with ffmpeg after the fact:
```bash
ffmpeg -y -i output.mp4 -c:v libx264 -c:a aac output_reencode.mp4
```

### OCR detects too much (blurring logos, UI text, etc.)
Increase confidence threshold:
```bash
python blur_subs.py input.mp4 output.mp4 --conf-thresh 0.4
```

### OCR misses subtitles
Try detecting more frequently:
```bash
python blur_subs.py input.mp4 output.mp4 --detect-every 5
```

---

## Notes / limitations
- This detects and masks *any* text it finds. It does not “know” what is subtitle text vs other on-screen text.
- OCR accuracy varies by resolution, compression artifacts, and font style.
- GPU mode depends on your PyTorch/CUDA environment and may not work out-of-the-box.

---

## License
Add a license file if you plan to distribute this publicly (MIT is common for small tools).
