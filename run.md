# Run the AivisSpeech Tanuki version

The new reminiscence voice demo is in `08_avisspeech`.

**Full instructions:** [08_avisspeech/run.md](08_avisspeech/run.md)

On the computer where setup was completed, open PowerShell and run:

```powershell
cd "C:\Users\suraj\Downloads\Tanuki\08_avisspeech"
.\start.ps1
```

Open [the robot viewer](http://127.0.0.1:8088/), wait for the connected message, and press **Speak**. The default is **Mao / Calm (まお・おちつき) at 0.90× speed**.

When finished, run this from the same folder:

```powershell
.\stop.ps1
```

For a fresh checkout or another computer, follow the full guide's first-time setup section before starting. It also covers troubleshooting, custom ports, manual operation and saved clips.

The tested Python setup is **Python 3.13.9 + NumPy 2.3.5**. NumPy is the only additional Python package required by the viewer server. Install it from [08_avisspeech/requirements.txt](08_avisspeech/requirements.txt):

```powershell
# Run from the 08_avisspeech folder above.
python -m pip install -r requirements.txt
```

AivisSpeech Engine 1.2.0 and Three.js 0.169.0 are separate downloads handled by `setup.ps1`. See the [complete dependency checklist](08_avisspeech/run.md#complete-library-and-software-checklist) for everything needed, including optional virtual-environment instructions.

For implementation details, see [08_avisspeech/ARCHITECTURE.md](08_avisspeech/ARCHITECTURE.md). Documentation for older versions remains in their respective folders.
