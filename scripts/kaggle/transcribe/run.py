"""Kernel Kaggle (GPU): chép lời ghi âm buổi hướng dẫn bằng faster-whisper large-v3, tiếng Việt, có mốc thời gian.

Đầu vào: dataset private (*.m4a) trong kernel-metadata.json (p3-audio-1023, p3-audio-1105). Đầu ra: /kaggle/working/<tên>.txt (mỗi dòng [mm:ss] câu)
và <tên>.json (đoạn + từ).
"""
import glob
import json
import subprocess
import sys
from pathlib import Path

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "faster-whisper==1.1.1"], check=True)
import numpy as np  # noqa: E402
from faster_whisper import WhisperModel  # noqa: E402

model = WhisperModel("large-v3", device="cuda", compute_type="float16")
for f in sorted(glob.glob("/kaggle/input/**/*.m4a", recursive=True)):
    # giải mã bằng ffmpeg: PyAV có sẵn trên Kaggle lệch phiên bản với faster-whisper (open() không nhận metadata_errors)
    raw = subprocess.run(["ffmpeg", "-nostdin", "-i", f, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, np.float32)
    segs, info = model.transcribe(audio, language="vi", beam_size=5, vad_filter=True,
                                  initial_prompt="Buổi hướng dẫn đồ án: CI/CD, GitHub Actions, log, nhãn, Maven, Gradle, "
                                                 "baseline, ablation, LLM, artifact, DevOps, HCL, BERT, UniXcoder, diff, commit, demo, RCA.")
    rows = []
    name = Path(f).stem
    with open(f"/kaggle/working/{name}.txt", "w", encoding="utf-8") as out:
        for s in segs:
            m, sec = divmod(int(s.start), 60)
            out.write(f"[{m:02d}:{sec:02d}] {s.text.strip()}\n")
            out.flush()
            rows.append({"start": s.start, "end": s.end, "text": s.text.strip()})
    Path(f"/kaggle/working/{name}.json").write_text(json.dumps({"duration": info.duration, "segments": rows},
                                                               ensure_ascii=False, indent=1), encoding="utf-8")
    print(name, f"{info.duration / 60:.1f} phút, {len(rows)} đoạn", flush=True)
