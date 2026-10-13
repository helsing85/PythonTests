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

`notepad_self_write` opens Windows Notepad and writes text using the keyboard.
