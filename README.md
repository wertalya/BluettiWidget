# BluettiWidget

An unofficial Windows 11 desktop widget for BLUETTI power stations. See charge,
input and output at a glance and open details for individual power readings
and a 10-minute history. The UI is in Ukrainian. [Інструкція українською](README.uk.md).

## Download for Windows 11

[**Download BluettiWidget-Setup.exe**](https://github.com/wertalya/BluettiWidget/releases/download/v0.4.2-preview/BluettiWidget-Setup.exe)
· [Release notes](https://github.com/wertalya/BluettiWidget/releases/tag/v0.4.2-preview)

Run the downloaded installer. Setup installs for the current Windows user,
adds a Start menu shortcut and shows the desktop widget on Windows sign-in by default.
Remove the app through **Settings → Apps → Installed apps**.

The portable build is available from [GitHub Actions](https://github.com/wertalya/BluettiWidget/actions/workflows/build.yml)
under **BluettiWidget-Windows-preview**.

## Compatibility

The app recognizes **29 BLUETTI models** over Bluetooth LE. Monitoring and
reconnection have been checked on an AC180P. The other 28 models are
experimental and read-only. See the [full list](docs/compatibility.md) and
[model setup](docs/compatibility.md#capacity-and-new-models). BLE works
directly without an API key, cloud login or MQTT broker.

## Updating

Use **Перевірити оновлення…** (Check for updates) in the widget menu, then
**Завантажити оновлення** to open the new installer download in your browser.
Quit the widget from its tray menu and install over the existing version in
the same directory. Do not uninstall first: `settings.ini` is preserved.
Keep the startup task selected if you want automatic startup.
Version 0.4.0 needs a one-time manual download using the link above.
Portable users can replace the closed EXE and keep their existing settings file.

The app checks automatically 30 seconds after launch, then every 6 hours. Recent
checks are remembered across restarts. Each new version gets one tray notification;
click it or use the update menu to download. Network failures stay silent and retry
on the next scheduled check. Disable **Автоматично перевіряти оновлення** in the
menu to opt out; manual checks remain available. Checks send no station data or settings. Preview users
receive newer preview or stable releases; stable users skip preview releases.
The application never installs updates silently.

The desktop widget now appears on Windows sign-in by default. Disable
**Показувати віджет після входу у Windows** under appearance settings for
tray-only startup. An explicit launch always opens the widget. The legacy
`--start-in-tray` flag is still available; installed shortcuts use `--autostart`.

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

## Share a model profile

Use **Запропонувати модель…** in the tray menu or open the
[model report form](https://github.com/wertalya/BluettiWidget/issues/new?template=model-request.yml).
Share the model, firmware, battery capacity and which readings work. Verified
registers and field names are welcome. Submissions are reviewed before they
become shared profiles. See [CONTRIBUTING.md](CONTRIBUTING.md).

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
.\build_installer.ps1
```

Folder build: `dist/BluettiWidget/BluettiWidget.exe`.
Single-file build: `portable/BluettiWidget.exe`.
The Inno Setup 6 compiler produces `dist/installer/BluettiWidget-Setup.exe`.
Both application builds embed the Windows app icon. Demo readings are synthetic.
GitHub Actions verifies setup and uploads the installer and portable preview.

Project code is MIT. See [THIRD_PARTY.md](THIRD_PARTY.md) for dependency licenses.
