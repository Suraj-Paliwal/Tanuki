# Run the Tanuki reminiscence voice demo

This guide starts **08_avisspeech**, the Tanuki robot with a local Japanese AivisSpeech voice and estimated lip sync. Commands below are for **Windows PowerShell**, unless stated otherwise.

## 1. Start on this computer

The engine, renderer, Python and NumPy were already installed and tested during setup. You normally only need these commands:

```powershell
cd "C:\Users\suraj\Downloads\Tanuki\08_avisspeech"
.\start.ps1
```

Open [the robot viewer](http://127.0.0.1:8088/) if it does not open automatically.

Wait for **AivisSpeech connected · Local voice** and for **Speak** to become available. The page automatically retries the connection every 10 seconds while disconnected. **Reconnect** retries immediately.

The expected starting settings are:

| Setting | Value |
| --- | --- |
| Voice & style | `まお · おちつき` — Mao / Calm |
| Speaking speed | `0.90×` |
| Lip-sync adjustment | `0 ms` additional adjustment |
| Text | A polite invitation to talk about songs from the past |

Enter a short Japanese sentence, then press **Speak**. The first request after starting the engine may take longer while it loads a voice model.

## 2. Understand what is running

There are two separate background programs:

| Program | Address | Purpose |
| --- | --- | --- |
| AivisSpeech Engine | `http://127.0.0.1:10101` | Converts Japanese text into voice audio |
| Tanuki server | `http://127.0.0.1:8088` | Serves the viewer and creates the matching mouth-animation track |

`start.ps1` starts the bundled engine if needed, starts the viewer server if port 8088 has no listener, and opens the viewer. It records the processes it manages in `runtime/engine.pid` and `runtime/server.pid`.

The terminal command can finish while both background programs continue running. Closing the browser does **not** stop them. These addresses work on this computer; the app does not currently expose a service to other devices.

To start without opening another browser window:

```powershell
.\start.ps1 -NoBrowser
```

## 3. Use the voice and playback controls

| Control | What it does |
| --- | --- |
| Voice & style | Selects one of the styles installed in AivisSpeech |
| Japanese text | Supplies the exact words the robot will speak, up to 160 characters |
| Speaking speed | Sets the next generated line's pace, from 0.50× to 1.50× in the viewer |
| Lip-sync adjustment | Moves mouth animation earlier or later during playback |
| Speak | Generates audio and a mouth track using the current text, voice and speed |
| Replay | Plays the last generated audio and mouth track again |
| Stop | Stops playback and returns the mouth to rest; also abandons a pending browser request |
| Download voice | Saves the generated WAV audio |
| Download lip-sync data | Saves the JSON response containing the mouth track and metadata |

After changing text, voice or speed, press **Speak** to generate the changed version. **Replay** uses the previous clip. Lip-sync adjustment applies during playback and does not require regenerating audio.

If the mouth is late, try a small **positive** adjustment, such as `+20 ms`. If it moves too early, try `−20 ms`. The slider adds to the driver's existing 30 ms anticipatory lead. This can correct a consistent offset; it cannot fix every incorrectly timed syllable.

The calm voice at 0.90× is a starting point for reminiscence conversations. Ask the listener whether the voice and pace suit them and adjust accordingly. The app speaks supplied text; it does not listen, understand responses, or generate a conversation by itself.

## 4. Stop and restart

From the same folder:

```powershell
.\stop.ps1
```

This stops the recorded server and bundled engine only when their process paths match this version. A separately launched AivisSpeech desktop app is managed through that app. A server launched manually in a terminal should be stopped with **Ctrl+C** in that terminal.

To restart after editing Python or changing the voice preset:

```powershell
.\stop.ps1
.\start.ps1
```

Refresh the browser after editing HTML or JavaScript. There is no automatic code reload. Refreshing restores the default voice, speed and text; user control changes are not saved across page reloads.

## 5. First-time setup on another Windows computer

Copy the complete `08_avisspeech` folder, including `model/`, `lib/`, `src/` and the launcher files. A Git checkout does not include downloaded `runtime/`, `vendor/` or generated `.media/` files; `setup.ps1` recreates the downloaded dependencies.

You need:

- Windows x64 for the bundled engine.
- Python available through the `python` command, with `pip`. This copy was tested with Python 3.13.
- PowerShell and a Windows `tar` that supports extracting 7z archives.
- A browser with WebGL support and a working audio output.
- Internet access for setup and the engine's first launch. Keep several GB free for the engine, voices and language assets; the final size depends on the installed models.

Check the commands in PowerShell:

```powershell
python --version
python -m pip --version
tar --version
```

Open PowerShell in your copied `08_avisspeech` folder, then run:

```powershell
.\setup.ps1
.\start.ps1
```

`setup.ps1` installs the dependency in `requirements.txt` into the Python environment selected by `python`. It downloads these pinned versions if their expected files are missing:

| Dependency | Version / source |
| --- | --- |
| NumPy | `>=1.24,<3`, through pip |
| AivisSpeech Engine | Windows x64 **1.2.0**, official GitHub release; archive SHA-256 is checked |
| Three.js | **0.169.0**, npm registry archive; served locally by the viewer |

The engine then downloads default voice models and language assets on its first startup. Wait for the connected message; first setup can take several minutes. CPU operation is the current default. No API key, Node.js installation, npm build or GPU is required for normal use. Node.js is only used for the optional JavaScript syntax check below.

If Python is available only in an Anaconda environment, use a PowerShell session with that environment activated before running setup and start. Both commands need to resolve to the same Python environment.

### Complete library and software checklist

The verified environment on this computer is **Python 3.13.9 (64-bit)** with **NumPy 2.3.5** on Windows. Use Python 3.13 (64-bit) to follow that tested setup. Other Python versions have not been verified for this demo.

| Software / library | Required? | How it is supplied |
| --- | --- | --- |
| Python 3.13, 64-bit, and pip | Yes | Install Python separately, or use an existing Anaconda environment. `setup.ps1` does not install Python itself. |
| **NumPy `>=1.24,<3`** | Yes; the only third-party Python package used by this server | Listed in [requirements.txt](requirements.txt). pip selects a release compatible with your Python. Tested here with 2.3.5. |
| AivisSpeech Engine **1.2.0**, Windows x64 | Yes for speech | Downloaded/extracted by `setup.ps1`, or supplied by your existing AivisSpeech installation. The tested bundled version is 1.2.0. |
| AivisSpeech voice models and language assets | Yes for speech | Downloaded by the engine at first launch. The preset requires the Mao model with its Calm style; another installed style is used if absent. |
| Three.js **0.169.0** | Yes for rendering | Downloaded by `setup.ps1` into `vendor/package/`. Loaded by the browser, not Python. |
| Three.js add-ons: GLTFLoader, RoomEnvironment, EffectComposer, RenderPass, ShaderPass, OutputPass | Yes; included with Three.js | Already contained in the same Three.js download. Do not install them separately. |
| Browser with WebGL and audio playback | Yes | Runs the page, renderer and browser audio APIs. |
| PowerShell | Yes for the supplied `.ps1` launchers | Starts setup, the engine and the viewer on Windows. |
| Windows `tar` with 7z support | Yes for automatic setup | Extracts the downloaded engine and renderer archives. See troubleshooting if the engine archive cannot be extracted. |
| Node.js | Optional | Only needed for `node --check src/app.js`; not used to run the viewer. |

Python's `argparse`, `hashlib`, `http.server`, `io`, `json`, `math`, `os`, `pathlib`, `random`, `re`, `sys`, `threading`, `unicodedata`, `urllib`, and `wave` modules come with Python. The tests also use built-in modules such as `unittest` and `tempfile`. Do **not** add these to pip requirements.

The `jp_kana`, `jp_lipsync`, and `align` modules are the files included in this project's `lib/` directory. They are local project code, not extra pip downloads.

The supplied prebuilt AivisSpeech executable packages its own engine runtime. You do not need to install its internal inference dependencies into the Python environment used by `server.py`.

For this version's documented run path, **Flask, FastAPI, Uvicorn, SciPy, PyTorch, Transformers, pykakasi, edge-tts, gTTS, ffmpeg, React and Blender do not need separate installation**. Some relate to other versions or to the engine's internal implementation. This server uses Python's built-in HTTP server, decodes its WAV data directly, and receives Japanese readings from AivisSpeech.

### Install just the Python requirements

From PowerShell:

```powershell
cd "C:\Users\suraj\Downloads\Tanuki\08_avisspeech"
python -m pip install -r requirements.txt
python -c "import sys, numpy; print('Python:', sys.version); print('NumPy:', numpy.__version__)"
```

This installs NumPy only. It does not download AivisSpeech or Three.js; use `setup.ps1` for the complete setup. On this already configured computer, rerunning the pip command is only necessary if the active Python environment is missing the dependency.

### Optional: use a separate Python environment

If you want this project's Python packages kept in their own folder, create a virtual environment before setup:

```powershell
cd "C:\Users\suraj\Downloads\Tanuki\08_avisspeech"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
.\setup.ps1
.\start.ps1
```

Activate that environment again in each new PowerShell session before running `start.ps1`. The launcher uses whichever `python` command is active. With the environment active, `setup.ps1` installs into it too; its repeated dependency-install step is safe when NumPy is already installed.

When finished:

```powershell
.\stop.ps1
deactivate
```

If PowerShell blocks activation scripts, you can still use the environment's interpreter directly for the manual server path:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe server.py
```

In that manual case, start the engine separately and make sure the Three.js files were downloaded as described in section 6. The virtual environment contains the viewer's Python dependency; it does not contain the engine's separately managed voice models.

## 6. Run manually or use an existing AivisSpeech app

This is useful for seeing live logs, using your existing engine, or running without the launcher scripts.

First complete dependency setup and make sure `vendor/package/build/three.module.js` exists. Opening `index.html` directly as a file will not work; use the local web address.

**Terminal 1 — voice engine:** open your installed AivisSpeech app and keep it running, or start the bundled engine from PowerShell:

```powershell
cd "C:\Users\suraj\Downloads\Tanuki\08_avisspeech"
& ".\runtime\Windows-x64\run.exe" --host 127.0.0.1 --port 10101 --output_log_utf8 --disable_sentry
```

**Terminal 2 — viewer server:**

```powershell
cd "C:\Users\suraj\Downloads\Tanuki\08_avisspeech"
python server.py
```

Open [http://127.0.0.1:8088](http://127.0.0.1:8088/). Keep both terminals open; use **Ctrl+C** in each when finished. If the engine is the desktop app, close it through its normal interface instead.

For an engine on a different local port or a different viewer port:

```powershell
python server.py --engine-url http://127.0.0.1:10102 --port 8089
```

This example assumes that you already started the engine on 10102. It does not change the engine's port. Visit `http://127.0.0.1:8089` for that viewer. `start.ps1` remains a launcher for the default ports, 10101 and 8088.

`server.py` also accepts `AIVISSPEECH_URL` as the engine address when `--engine-url` is omitted. Prefer the explicit command above when troubleshooting.

## 7. Check that everything is connected

Run these read-only checks from PowerShell:

```powershell
# Engine version; expected installed version is 1.2.0.
Invoke-RestMethod "http://127.0.0.1:10101/version"

# Viewer connection and configured defaults.
Invoke-RestMethod "http://127.0.0.1:8088/api/status" | Format-List

# Installed voice names and style IDs.
(Invoke-RestMethod "http://127.0.0.1:8088/api/voices").voices | Format-Table
```

A working viewer reports `ready: True`, `default_voice: 888753763` for the currently installed Mao / Calm style, and `default_speed: 0.9`. The voice list can change when models are installed or removed. If the calm style is absent, the first installed style is selected instead.

Then use **Speak** in the browser. You should hear the line, see the mouth and vowel meters move, and see the status return to ready at the end. **Stop** should close the mouth. This checks operation; it does not prove exact syllable alignment.

## 8. Troubleshooting

| Symptom | What to do |
| --- | --- |
| `python` is not recognized | Open the terminal for your installed Python/Anaconda environment, or install Python and make its command available. Confirm `python --version` works before continuing. |
| `No module named numpy` | From this folder, run `python -m pip install -r requirements.txt` using the same Python that will start the server. |
| PowerShell refuses to run `.ps1` scripts | Use the manual startup instructions if the dependencies are already present. On a managed computer, use the approved script-execution procedure for setup. |
| 7z extraction fails during setup | Use a Windows tar with 7z support, or extract `runtime/engine.7z` with 7-Zip into `runtime/`. The resulting executable must be `runtime/Windows-x64/run.exe`. Then rerun setup for any remaining dependencies. |
| Download or checksum error | Check the network and rerun setup. A checksum mismatch must be resolved before using that download. The setup script redownloads the archive when the extracted engine is missing. |
| Viewer does not open | Start the server, then enter `http://127.0.0.1:8088/` in the browser. Do not double-click `index.html`. |
| Viewer stays at loading | Check the server log for missing files. Confirm `model/tanuki.gltf`, `model/tanuki.bin`, all three model textures and `vendor/package/build/three.module.js` exist. Run setup if the renderer is missing; refresh the page. |
| AivisSpeech is not ready | Allow first-run downloads to finish. Check the engine log below and the `/version` check above. Keep the engine open and click Reconnect. |
| No voices / calm voice is missing | Finish the engine's initial model installation, or install the required voice through AivisSpeech. Reconnect to refresh the list. The application only shows installed styles. |
| Wrong page opens at 8088 / address already in use | Another application may own the port. `start.ps1` skips starting its server if anything is already listening there. Use the manual `--port 8089` example and visit that address, or stop the known conflicting application. |
| Text is rejected | Use 1–160 characters of pronounceable Japanese. Split longer passages into short requests. A generated clip over 45 seconds is also rejected. |
| Voice synthesis is slow | Wait for the first model load and try a shorter sentence. Requests are serialized to the engine. Stopping the browser request does not necessarily stop synthesis already underway. |
| No sound | Check the computer's output device, volume and tab mute setting. Click Speak or Replay; playback needs a user interaction. Check the page message and server log if it still fails. |
| Mouth is early or late | Adjust the lip-sync slider in small steps and replay. Longer expressive speech can still have local timing errors because the alignment is estimated. |
| Changed the voice but hear the old one | Press Speak. Replay intentionally uses the last generated clip. |
| Changes disappear after refresh | Only the built-in defaults persist. To change those defaults, follow [the configuration notes](ARCHITECTURE.md#configuration). |

## 9. Logs, saved clips and backups

From PowerShell in `08_avisspeech`:

```powershell
Get-Content .\runtime\engine.stdout.log -Tail 40
Get-Content .\runtime\engine.stderr.log -Tail 40
Get-Content .\runtime\server.stdout.log -Tail 40
Get-Content .\runtime\server.stderr.log -Tail 40
```

The launchers redirect output to these files; later launches can replace previous log contents. Copy a relevant log before restarting if you want to retain it. Manual terminal launches show output in the terminal instead.

| Location | Contents |
| --- | --- |
| `.media/` | Generated WAV files and matching JSON responses, including the Japanese reading |
| `demo/greeting.wav` and `.json` | Earlier normal-voice verification sample |
| `demo/reminiscence.wav` and `.json` | Mao / Calm at 0.90×, using the reminiscence prompt |
| `runtime/` | Downloaded engine, archives, launcher logs and process IDs |
| `vendor/` | Downloaded Three.js renderer |
| `%APPDATA%\AivisSpeech-Engine\` | Engine-managed voice models, settings, dictionary data and logs |

Engine language assets may also use the standard user cache. Copying this project alone does not guarantee that all engine-managed voice assets are available offline on a different computer. Run and test it online once there before relying on offline use.

Save the WAV and JSON together when retaining a spoken line. The JSON's `audio` field points to the original `/media/...` route, not a portable absolute file path; if you move a sample, supply its new audio location alongside `response.track`.

Generated media remains on disk until you manage it yourself; there is no automatic cleanup or retention limit. Back up any clips you want before clearing generated files. Restarting clears the in-memory response cache but does not delete the files.

## 10. Optional development checks

These commands do not require the live engine:

```powershell
python -m unittest discover -s tests -v
```

If Node.js is installed:

```powershell
node --check src/app.js
```

See [VALIDATION.md](VALIDATION.md) for the recorded live-engine and browser checks, and [ARCHITECTURE.md](ARCHITECTURE.md) for API details and how the voice drives the mouth.
