# BluettiWidget

An unofficial Windows 11 desktop widget for BLUETTI power stations. See charge,
input and output at a glance and open details for individual power readings
and a 10-minute history. The UI is in Ukrainian. [Інструкція українською](README.uk.md).

## Compatibility

| Model | Monitoring | Controls |
| --- | --- | --- |
| AC180P | Monitoring was tested on one physical station in the previous preview | AC/DC and charge mode for unencrypted BLE. Physical switching awaits validation |
| AC180 | Experimental | Read-only |
| AC2A, AC60, AC70, AC70P, AC200L, EB3A | Experimental. Register maps checked offline against the bundled protocol library | Read-only |

Compatibility can vary by firmware and Bluetooth adapter. Encrypted BLE uses
the upstream reader on a slower schedule and is read-only. The widget uses BLE
directly and requires no API keys, cloud login or MQTT broker. It runs on
Windows. The S/M/L presets fit different Windows screen and widget sizes.

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
- The Windows taskbar uses the app icon while the widget is visible. The tray
  icon displays the state of charge. If telemetry stops, the widget marks the
  last readings and retries automatically.

## Capacity and model profiles

AC180P and AC180 have default capacities of 1440 Wh and 1152 Wh. Set an
override in the local `settings.ini` under `[capacity_wh]` using the model as
the key. See [settings.example.ini](settings.example.ini). Restart the app to
apply the override. The runtime estimate uses capacity, recent output and
conversion-loss assumptions. It is hidden when the capacity or required
readings are missing, during charging and when readings are stale.

To add a model, start with its device class in the pinned `bluetti-bt-lib`
registry and add a read-only `StationProfile` in `models.py`. The default
plan derives the charge and power registers from that class. Use `aliases`
for fields with different names, and `read_blocks` for firmware that needs
specific register groups. Verify the advertised name, then compare charge,
power and reconnect behavior with the official app on hardware. See
[CONTRIBUTING.md](CONTRIBUTING.md).

The executable stores the BLE address in `settings.ini` and diagnostic logs in
`logs/` beside itself. Use a writable folder. Keep your settings, device ID,
address and raw diagnostics out of Git and public issue reports.

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
