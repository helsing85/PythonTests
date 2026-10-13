#!/usr/bin/env python3
"""
Wyciąga polskie ścieżki dźwiękowe (oraz ścieżki bez określonego języka)
z plików wideo we wskazanym folderze i wszystkich podfolderach.

Użycie:
    python wyciagnij_polskie_audio.py                 -> wartości DEFAULT_* poniżej
    python wyciagnij_polskie_audio.py "D:\\Filmy"      -> podany folder
    python wyciagnij_polskie_audio.py "D:\\Filmy" -o "D:\\Audio"   -> zapis do innego folderu
    python wyciagnij_polskie_audio.py "D:\\Filmy" --ffmpeg "C:\\ffmpeg\\bin"  -> własny FFmpeg

Edytuj DEFAULT_FOLDER, aby wskazać folder z filmami (np. r"D:\\Filmy").
Puste DEFAULT_FOLDER otwiera okno wyboru folderu.
DEFAULT_OUTPUT = None zapisuje audio obok filmów, a DEFAULT_FFMPEG = None
włącza automatyczne wyszukiwanie narzędzi. Argumenty z terminala mają pierwszeństwo.

Wymaga ffmpeg/ffprobe (w PATH, obok skryptu lub podanych przez --ffmpeg).
Skrypt nie pobiera tych narzędzi automatycznie.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

DEFAULT_FOLDER = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT = ""
DEFAULT_FFMPEG = None
DEFAULT_OVERWRITE = False

VIDEO_EXT = {
    ".mkv", ".mp4", ".m4v", ".avi", ".mov", ".wmv", ".ts", ".m2ts", ".mts",
    ".webm", ".flv", ".mpg", ".mpeg", ".vob", ".ogm", ".3gp", ".divx", ".rmvb",
}
POLISH_TAGS = {"pol", "pl", "polish", "polski", "pl-pl"}
UNDEFINED_TAGS = {"", "und", "unk", "unknown", "mis", "zxx"}

# kodek -> (rozszerzenie, dodatkowe argumenty ffmpeg)
CODEC_EXT = {
    "ac3": (".ac3", []),
    "eac3": (".eac3", []),
    "dts": (".dts", []),
    "truehd": (".thd", []),
    "mlp": (".mlp", []),
    "aac": (".m4a", []),
    "mp3": (".mp3", []),
    "mp2": (".mp2", []),
    "flac": (".flac", []),
    "opus": (".opus", []),
    "vorbis": (".ogg", []),
    "alac": (".m4a", []),
}

SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
# ---------------------------------------------------------------- ffmpeg ---
def is_tool_file(path):
    return os.path.isfile(path) and (os.name == "nt" or os.access(path, os.X_OK))


def find_tool(name):
    exe = name + (".exe" if os.name == "nt" else "")
    for cand in (os.path.join(SCRIPT_DIR, exe), os.path.join(SCRIPT_DIR, "ffmpeg", exe)):
        if is_tool_file(cand):
            return cand
    return shutil.which(name)


def tools_from_user_path(path):
    """Przyjmuje ścieżkę do ffmpeg.exe albo do folderu z ffmpeg/ffprobe."""
    path = os.path.abspath(path.strip().strip('"'))
    if not os.path.exists(path):
        sys.exit("Podana ścieżka do ffmpeg nie istnieje: {}".format(path))
    folder = path if os.path.isdir(path) else os.path.dirname(path)
    suffix = ".exe" if os.name == "nt" else ""
    found = []
    for name in ("ffmpeg", "ffprobe"):
        cands = [os.path.join(folder, name + suffix), os.path.join(folder, "bin", name + suffix)]
        if name == "ffmpeg" and is_tool_file(path):
            cands.insert(0, path)
        tool = next((c for c in cands if is_tool_file(c)), None)
        if not tool:
            sys.exit("Nie znaleziono wykonywalnego {} w: {}".format(name + suffix, folder))
        found.append(tool)
    return found[0], found[1]


def ensure_ffmpeg(user_path=None):
    if user_path:
        return tools_from_user_path(user_path)
    ffmpeg, ffprobe = find_tool("ffmpeg"), find_tool("ffprobe")
    if ffmpeg and ffprobe:
        return ffmpeg, ffprobe
    missing = [name for name, tool in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)) if not tool]
    if os.name == "nt":
        hint = "Zainstaluj FFmpeg (np. 'winget install Gyan.FFmpeg') lub wskaż jego folder przez --ffmpeg."
    else:
        hint = "Zainstaluj FFmpeg (np. 'sudo apt install ffmpeg') lub wskaż jego folder przez --ffmpeg."
    sys.exit("Brak {}. {}".format(" i ".join(missing), hint))


# --------------------------------------------------------------- helpers ---
def run(cmd):
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)


def probe(ffprobe, path):
    res = run([ffprobe, "-v", "error", "-print_format", "json",
               "-show_streams", "-show_format", path])
    if res.returncode != 0:
        raise RuntimeError(res.stderr.decode("utf-8", "replace").strip())
    return json.loads(res.stdout.decode("utf-8", "replace"))


def tags_ci(stream):
    return {k.lower(): v for k, v in (stream.get("tags") or {}).items()}


def parse_rate(rate):
    try:
        num, den = rate.split("/")
        num, den = float(num), float(den)
        return num / den if den else 0.0
    except (ValueError, AttributeError):
        return 0.0


def get_fps(info):
    for s in info.get("streams", []):
        if s.get("codec_type") != "video":
            continue
        if (s.get("disposition") or {}).get("attached_pic"):
            continue  # okładka, nie film
        fps = parse_rate(s.get("avg_frame_rate")) or parse_rate(s.get("r_frame_rate"))
        if fps:
            return fps
    return None


def format_fps(fps):
    if fps is None:
        return "brak-fps"
    s = "{:.3f}".format(fps).rstrip("0").rstrip(".")
    return s + "fps"


def get_duration(info):
    dur = (info.get("format") or {}).get("duration")
    try:
        if dur:
            return float(dur)
    except ValueError:
        pass
    # fallback: tag DURATION ze strumieni MKV, np. "01:52:34.123000000"
    best = 0.0
    for s in info.get("streams", []):
        d = tags_ci(s).get("duration")
        if d:
            m = re.match(r"(\d+):(\d+):(\d+(?:\.\d+)?)", d)
            if m:
                best = max(best, int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)))
    return best or None


def format_duration(sec):
    if sec is None:
        return "brak-czasu"
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return "{:02d}h{:02d}m{:02d}s".format(h, m, s)


def sanitize(text):
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    return text[:100]


def track_comment(tags):
    parts = []
    for key in ("title", "comment", "handler_name"):
        val = (tags.get(key) or "").strip()
        if not val or val in parts:
            continue
        if key == "handler_name" and val.lower() in ("soundhandler", "sound handler", "core media audio"):
            continue  # domyślne, nic nie mówiące nazwy w MP4
        parts.append(val)
    return " - ".join(parts)


# ----------------------------------------------------------------- core ----
def process_file(ffmpeg, ffprobe, path, root, out_root, overwrite):
    info = probe(ffprobe, path)
    fps_txt = format_fps(get_fps(info))
    dur_txt = format_duration(get_duration(info))
    base = os.path.splitext(os.path.basename(path))[0]

    if out_root:
        rel_dir = os.path.relpath(os.path.dirname(path), root)
        out_dir = os.path.normpath(os.path.join(out_root, rel_dir))
    else:
        out_dir = os.path.dirname(path)

    audio = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    found = 0
    for a_idx, s in enumerate(audio):
        tags = tags_ci(s)
        lang = (tags.get("language") or "").strip().lower()
        if lang in POLISH_TAGS:
            lang_txt = "PL"
        elif lang in UNDEFINED_TAGS:
            lang_txt = "brak-jezyka"
        else:
            continue
        found += 1

        codec = s.get("codec_name") or "unknown"
        if codec.startswith("pcm_"):
            ext, extra = ".wav", []
        else:
            ext, extra = CODEC_EXT.get(codec, (".mka", []))

        channels = s.get("channels")
        name_parts = [base, "audio{}".format(a_idx + 1), lang_txt]
        comment = track_comment(tags)
        if comment:
            name_parts.append(comment)
        name_parts.append(codec + (" {}ch".format(channels) if channels else ""))
        name_parts += [fps_txt, dur_txt]
        out_name = sanitize(base) + "".join(" [{}]".format(sanitize(p)) for p in name_parts[1:])
        out_path = os.path.join(out_dir, out_name + ext)

        if os.path.exists(out_path) and not overwrite:
            print("    = pominięto (istnieje): {}".format(os.path.basename(out_path)))
            continue
        os.makedirs(out_dir, exist_ok=True)
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", path,
               "-map", "0:{}".format(s["index"]), "-vn", "-sn", "-dn",
               "-map_metadata", "-1", "-c:a", "copy"] + extra + [out_path]
        res = run(cmd)
        if res.returncode != 0 and ext != ".mka":
            # awaryjnie: kontener Matroska przyjmie prawie każdy kodek
            out_path = os.path.splitext(out_path)[0] + ".mka"
            cmd[-1] = out_path
            res = run(cmd)
        if res.returncode == 0:
            print("    + {}".format(os.path.basename(out_path)))
        else:
            print("    ! BŁĄD ścieżki {}: {}".format(a_idx + 1, res.stderr.decode("utf-8", "replace").strip()[:300]))
    if not found:
        print("    (brak polskich / nieoznaczonych ścieżek)")
    return found


def pick_folder():
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="Wybierz folder z filmami")
        root.destroy()
        return folder
    except Exception:
        return input("Podaj ścieżkę do folderu z filmami: ").strip().strip('"')


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Wyciąga polskie (i nieoznaczone) ścieżki audio z plików wideo.")
    p.add_argument("folder", nargs="?", default=DEFAULT_FOLDER,
                   help="folder do przeszukania (domyślnie DEFAULT_FOLDER; pusty: okno wyboru)")
    p.add_argument("-o", "--output", default=DEFAULT_OUTPUT,
                   help="folder docelowy (domyślnie DEFAULT_OUTPUT lub obok pliku wideo; struktura podfolderów zachowana)")
    p.add_argument("-f", "--overwrite", action="store_true", default=DEFAULT_OVERWRITE, help="nadpisuj istniejące pliki")
    p.add_argument("--ffmpeg", metavar="ŚCIEŻKA", default=DEFAULT_FFMPEG,
                   help="ścieżka do ffmpeg lub folderu zawierającego ffmpeg i ffprobe")
    args = p.parse_args()

    folder = args.folder or pick_folder()
    if not folder or not os.path.isdir(folder):
        sys.exit("Nie wskazano poprawnego folderu.")
    folder = os.path.abspath(folder)
    out_root = os.path.abspath(args.output) if args.output else None

    ffmpeg, ffprobe = ensure_ffmpeg(args.ffmpeg)
    print("Folder: {}\n".format(folder))

    videos = []
    for dirpath, dirnames, filenames in os.walk(folder):
        if out_root and os.path.abspath(dirpath).startswith(out_root):
            continue
        for fn in sorted(filenames):
            if os.path.splitext(fn)[1].lower() in VIDEO_EXT:
                videos.append(os.path.join(dirpath, fn))

    total_tracks = errors = 0
    for i, path in enumerate(videos, 1):
        print("[{}/{}] {}".format(i, len(videos), os.path.relpath(path, folder)))
        try:
            total_tracks += process_file(ffmpeg, ffprobe, path, folder, out_root, args.overwrite)
        except Exception as e:
            errors += 1
            print("    ! BŁĄD: {}".format(e))

    print("\nGotowe. Plików wideo: {}, ścieżek do wyciągnięcia: {}, błędów plików: {}".format(
        len(videos), total_tracks, errors))


if __name__ == "__main__":
    try:
        main()
    finally:
        if os.name == "nt" and len(sys.argv) == 1:
            input("\nNaciśnij Enter, aby zamknąć...")
