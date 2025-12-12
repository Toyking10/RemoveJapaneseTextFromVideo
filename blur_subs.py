#!/usr/bin/env python3
import argparse
from pathlib import Path
import subprocess

import cv2
import numpy as np
from easyocr import Reader


def parse_args():
    p = argparse.ArgumentParser(
        description="Blur or black out text (e.g. hard-coded subs) in a video."
    )
    p.add_argument("input", help="Input video file path")
    p.add_argument("output", help="Output video file path")
    p.add_argument(
        "--mode",
        choices=["blur", "black"],
        default="blur",
        help="How to hide text: blur region or fill with black",
    )
    p.add_argument(
        "--band-ratio",
        type=float,
        default=1,
        help="(Currently unused) Previously limited detection to bands; now detection runs on the full frame.",
    )
    p.add_argument(
        "--detect-every",
        type=int,
        default=10,
        help="Run text detection every N frames (reuse boxes in between) to speed up",
    )
    p.add_argument(
        "--conf-thresh",
        type=float,
        default=0.0,
        help="Minimum OCR confidence to treat a region as text",
    )
    p.add_argument(
        "--gpu",
        action="store_true",
        help="Use GPU for EasyOCR if available (default: CPU)",
    )
    return p.parse_args()


def ensure_video_writer(output_path, fourcc_str, fps, frame_size):
    fourcc = cv2.VideoWriter_fourcc(*fourcc_str)
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, frame_size)
    if not writer.isOpened():
        raise RuntimeError(f"Failed to open VideoWriter for: {output_path}")
    return writer


def blur_or_black(frame, boxes, mode):
    h, w = frame.shape[:2]

    for (x1, y1, x2, y2) in boxes:
        # Clamp to frame bounds
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w - 1, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h - 1, y2))

        if x2 <= x1 or y2 <= y1:
            continue

        roi = frame[y1:y2, x1:x2]

        if mode == "blur":
            # Kernel size must be odd and > 0
            ksize = max(15, (x2 - x1) // 3 | 1)  # simple heuristic
            ksize = ksize if ksize % 2 == 1 else ksize + 1
            blurred = cv2.GaussianBlur(roi, (ksize, ksize), 0)
            frame[y1:y2, x1:x2] = blurred
        else:  # "black"
            frame[y1:y2, x1:x2] = 0

    return frame


def detect_text_boxes(frame, reader, band_ratio, conf_thresh):
    """
    Detect text anywhere in the frame using EasyOCR.
    Returns a list of (x1, y1, x2, y2) in full-frame coordinates.
    band_ratio is currently ignored.
    """
    h, w = frame.shape[:2]
    boxes = []

    results = reader.readtext(frame, detail=1)
    for res in results:
        bbox, text, conf = res
        if conf < conf_thresh:
            continue
        
        xs = [int(p[0]) for p in bbox]
        ys = [int(p[1]) for p in bbox]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)

        # Clamp just in case OCR returns slightly out-of-bounds coords
        x1 = max(0, min(w - 1, x1))
        x2 = max(0, min(w - 1, x2))
        y1 = max(0, min(h - 1, y1))
        y2 = max(0, min(h - 1, y2))

        if x2 <= x1 or y2 <= y1:
            continue
        min_w, min_h = 10, 10  # tweak
        if (x2 - x1) < min_w or (y2 - y1) < min_h:
            continue
        boxes.append((x1, y1, x2, y2))

    return boxes


def mux_audio(input_path: Path, video_only_path: Path, output_path: Path):
    """Use ffmpeg to combine processed video with original audio.

    Requires ffmpeg to be available in PATH. If ffmpeg is missing or fails,
    fall back to leaving the video-only file as the final output.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_only_path),
        "-i", str(input_path),
        "-map", "0:v:0",
        "-map", "1:a?",
        "-c:v", "copy",
        "-c:a", "copy",
        str(output_path),
    ]
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        print("ffmpeg not found; leaving video without audio.")
        video_only_path.replace(output_path)
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg failed ({e}); leaving video without audio.")
        video_only_path.replace(output_path)
    else:
        # Cleanup temporary video-only file
        try:
            video_only_path.unlink()
        except OSError:
            pass


def main():
    args = parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    # Temporary file for video-only output; audio will be muxed back in with ffmpeg.
    temp_video_path = output_path.with_name(output_path.stem + "_video_only" + output_path.suffix)

    if not input_path.is_file():
        print(f"Input file not found: {input_path}")
        raise SystemExit(1)

    # Initialize EasyOCR (ja + en for JP YouTube, but we hide any text anyway)
    print("Initializing OCR reader... (first run may download models)")
    reader = Reader(["ja", "en"], gpu=args.gpu)

    cap = cv2.VideoCapture(str(input_path))
    if not cap.isOpened():
        print(f"Failed to open input video: {input_path}")
        raise SystemExit(1)

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frame_size = (width, height)

    # mp4v works decently on macOS/Windows; you can change if needed
    print(f"Input resolution: {width}x{height}, FPS: {fps:.2f}")
    writer = ensure_video_writer(temp_video_path, "mp4v", fps, frame_size)

    frame_idx = 0
    last_boxes = []
    empty_streak = 0

    print("Processing video...")
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        # Only run detection every N frames to save time
        if frame_idx % args.detect_every == 0:
            new_boxes = detect_text_boxes(
                frame,
                reader,
                band_ratio=args.band_ratio,
                conf_thresh=args.conf_thresh,
            )

            if new_boxes:
                # We detected some text this time: update boxes and reset empty streak.
                last_boxes = new_boxes
                empty_streak = 0
            else:
                # No text detected this time: increase empty streak.
                empty_streak += 1
                # After a few consecutive empty detections, clear the boxes
                # so the blur bar doesn't hang around forever after text disappears.
                if empty_streak >= 3:
                    last_boxes = []

        frame = blur_or_black(frame, last_boxes, args.mode)
        writer.write(frame)

        frame_idx += 1
        if frame_idx % 100 == 0:
            print(f"  Processed {frame_idx} frames...", end="\r")

    cap.release()
    writer.release()

    # Mux original audio back into the processed video using ffmpeg.
    mux_audio(input_path, temp_video_path, output_path)

    print(f"\nDone. Output written to: {output_path}")


if __name__ == "__main__":
    main()
