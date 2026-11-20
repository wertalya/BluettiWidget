# BluettiWidget

An unofficial Windows 11 desktop widget for BLUETTI power stations. See charge,
input and output at a glance and open details for individual power readings
and a 10-minute history. The UI is in Ukrainian. [Інструкція українською](README.uk.md).

## Download for Windows 11

Open [Windows build runs](https://github.com/wertalya/BluettiWidget/actions/workflows/build.yml),
choose the latest successful run and download the `BluettiWidget-Windows-preview`
artifact. GitHub may require sign-in to download Actions artifacts.
Extract the archive and run `portable/BluettiWidget.exe`.

## Compatibility

The app recognizes **29 BLUETTI models** over Bluetooth LE. Monitoring and
reconnection have been checked on an AC180P. The other 28 models are
experimental and read-only. See the [full list](docs/compatibility.md) and
[model setup](docs/compatibility.md#capacity-and-new-models). BLE works
directly without an API key, cloud login or MQTT broker.

## Run from source

Use Python 3.12 and a Bluetooth LE adapter.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe widget.py
```

The connection window scans automatically on first launch. Turn on Bluetooth
on the PC and the station, select the station from the list and click
**Підключити**. If the station is busy, close its connection in the BLUETTI phone
app. The widget remembers the station when it receives a valid charge reading.

- **Станція** opens the Bluetooth picker again. **↗** shows details and history.
- **Телефон** releases Bluetooth for the phone. **Повернути** reconnects the widget.
- **···** changes the size, opacity and placement. **×** hides the widget to the
  system tray. Use the tray icon to show it again, or its menu to quit.
- The tray icon displays the state of charge. Right-click it to manage
  connection and appearance. The widget stays off the taskbar by default.
  Enable **Показувати на панелі завдань** under **Вигляд і положення** to
  keep a taskbar button while the widget is visible.
- If telemetry stops, the widget marks the last readings and retries automatically.

## Local settings

Set battery capacity in [settings.example.ini](settings.example.ini) by copying
the relevant section to your local `settings.ini`. The executable stores your
BLE address and rotating diagnostic logs beside itself. Use a writable folder.
Keep settings, device identifiers and raw logs out of Git and public issues.

## Build and check

```powershell
.\.venv\Scripts\python.exe -m unittest check_widget test_models test_feedback
.\.venv\Scripts\python.exe widget.py --demo
.\.venv\Scripts\python.exe -m pip install pyinstaller==6.22.3
.\build.ps1
.\.venv\Scripts\python.exe build_portable.py
```

Folder build: `dist/BluettiWidget/BluettiWidget.exe`.
Single-file build: `portable/BluettiWidget.exe`.
Both builds embed the Windows app icon. Demo readings are synthetic.
GitHub Actions runs the offline tests and uploads the portable preview.

Project code is MIT. See [THIRD_PARTY.md](THIRD_PARTY.md) for dependency licenses.
