"""Stage 5: render shots + voice + captions (+ optional music) into a 1080x1920 MP4."""

from __future__ import annotations

import random
import subprocess
from pathlib import Path

from .config import FPS, HEIGHT, MUSIC_DIR, WIDTH, ffmpeg_bin
from .languages import MAC_FONTS

ENCODE = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"]


def run(args: list[str], cwd: Path) -> None:
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", *args]
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{' '.join(cmd)}\n{result.stderr[-2000:]}")


def image_shot(src: str, frames: int, index: int, out: Path) -> None:
    """Ken Burns over the image, letterboxed onto a blurred copy of itself."""
    big_w, big_h = WIDTH * 2, HEIGHT * 2  # zoompan jitters less when it works at 2x
    zoom = 0.16
    z = f"1+{zoom}*on/{frames}" if index % 2 == 0 else f"{1 + zoom}-{zoom}*on/{frames}"
    # Drift slightly left or right so consecutive stills don't feel identical.
    x = "iw/2-(iw/zoom/2)" + ("+on*0.6" if index % 4 < 2 else "-on*0.6")
    graph = (
        f"[0:v]scale=540:960:force_original_aspect_ratio=increase,crop=540:960,"
        f"boxblur=20:2,scale={big_w}:{big_h},setsar=1[bg];"
        # Fit the image, but never let a landscape photo shrink below 58% of the frame height;
        # crop its sides instead (a thin strip in a tall frame reads as "nothing on screen").
        f"[0:v]scale=-2:'min({big_h},max({big_w}*ih/iw,{big_h}*0.58))',"
        f"crop='min(iw,{big_w})':ih,setsar=1[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"zoompan=z='{z}':x='max(0,min({x},iw-iw/zoom))':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS},format=yuv420p[v]"
    )
    run(["-i", src, "-filter_complex", graph, "-map", "[v]", "-frames:v", str(frames),
         *ENCODE, "-an", str(out)], out.parent)


def video_shot(src: str, frames: int, out: Path) -> None:
    vf = (f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},"
          f"fps={FPS},setsar=1,format=yuv420p")
    run(["-stream_loop", "-1", "-i", src, "-vf", vf, "-frames:v", str(frames),
         *ENCODE, "-an", str(out)], out.parent)


def render(shots: list[dict], out_dir: Path, total: float, music: bool = True,
           fonts_dir: str = MAC_FONTS) -> Path:
    seg_dir = out_dir / "segments"
    seg_dir.mkdir(exist_ok=True)
    listing = []
    for i, shot in enumerate(shots):
        # Frame counts come from cumulative times so rounding never drifts away from the audio.
        first = round(shot["start"] * FPS)
        last = round((shot["start"] + shot["duration"]) * FPS)
        frames = max(1, last - first)
        seg = seg_dir / f"{i:03d}.mp4"
        if shot["type"] == "image":
            image_shot(shot["path"], frames, i, seg)
        else:
            video_shot(shot["path"], frames, seg)
        listing.append(f"file '{seg.name}'\n")
    (seg_dir / "list.txt").write_text("".join(listing))
    run(["-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", str(out_dir / "visuals.mp4")],
        seg_dir)

    tracks = sorted(p for p in MUSIC_DIR.glob("*") if p.suffix.lower() in (".mp3", ".m4a", ".wav"))
    inputs = ["-i", "visuals.mp4", "-i", "voice.mp3"]
    norm = "loudnorm=I=-14:TP=-1.5:LRA=11"
    if music and tracks:
        inputs += ["-stream_loop", "-1", "-i", str(random.choice(tracks))]
        # Music sits low and ducks further whenever the narrator speaks.
        audio = (f"[2:a]volume=0.22[m];[m][1:a]sidechaincompress=threshold=0.04:ratio=10:"
                 f"attack=15:release=350[duck];"
                 f"[1:a][duck]amix=inputs=2:duration=first:normalize=0,{norm}[a]")
    else:
        audio = f"[1:a]{norm}[a]"
    graph = f"[0:v]ass=captions.ass:fontsdir={fonts_dir}[v];{audio}"
    final = out_dir / "final.mp4"
    run([*inputs, "-filter_complex", graph, "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
         "-profile:v", "high", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", final.name], out_dir)
    run(["-ss", "0.8", "-i", final.name, "-frames:v", "1", "-q:v", "2", "thumb.jpg"], out_dir)
    return final


def duration(path: Path) -> float:
    out = subprocess.run([ffmpeg_bin("ffprobe"), "-v", "error", "-show_entries",
                          "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True)
    return float(out.stdout.strip())
