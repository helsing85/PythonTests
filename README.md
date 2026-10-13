# PythonTests

## ExtractAudio web interface

Run the local web UI from the repository root.

Windows PowerShell:

```powershell
python .\ExtractAudio\webui\server.py
```

Linux:

```bash
python3 ExtractAudio/webui/server.py
```

Open http://127.0.0.1:8765. The UI launches the existing extraction script as
a subprocess; it does not modify the script. Stop the web server with Ctrl+C.

FFmpeg and FFprobe must be available on `PATH` or provided in the UI. On
Debian/Ubuntu, install them with `sudo apt install ffmpeg`. On Windows, install
them with `winget install Gyan.FFmpeg` or provide their folder in the UI. The
script does not download these tools automatically.

## Build executable

Build separately on each target operating system; PyInstaller does not cross-compile.

Windows PowerShell:

```powershell
python -m pip install PyInstaller
python -m PyInstaller --clean --noconfirm audio_extract_webui.spec
```

Linux:

```bash
python3 -m pip install PyInstaller
python3 -m PyInstaller --clean --noconfirm audio_extract_webui.spec
```

The executable is written to `dist/AudioExtract.exe` on Windows or
`dist/AudioExtract` on Linux. Starting it opens the web UI in the default
browser. FFmpeg and FFprobe are not bundled; select their location in the UI.

`notepad_self_write` opens Windows Notepad and writes text using the keyboard.
