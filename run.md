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

For implementation details, see [08_avisspeech/ARCHITECTURE.md](08_avisspeech/ARCHITECTURE.md). Documentation for older versions remains in their respective folders.
