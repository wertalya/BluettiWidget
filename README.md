# BluettiWidget

A compact Windows desktop widget for BLUETTI power stations. Built for quick,
readable monitoring: charge, power, estimated runtime and Bluetooth handoff.

**Early preview. Windows 11. UI language: Ukrainian.** English UI is planned.

## Compatibility

| Station | Monitoring | Controls | Hardware status |
|---|---|---|---|
| AC180P | Implemented | AC/DC and charge mode implemented | Monitoring tested on one owner's station; physical switching not tested |
| AC180 | Experimental | Disabled | Register map checked against upstream library; no hardware test |
| Other BLUETTI models | Not yet supported | Disabled | Model profiles and owner testing required |
| Other brands | Planned | Not supported | Separate protocol adapters required |

Firmware compatibility can vary. Encrypted connections use the upstream reader
and slower polling; writes are disabled. An upstream supported-model list is
not a claim that this application has tested those models.

## Features

- Smooth instrument needles and power values; target polling every 0.5 seconds.
- Charge indicator in the Windows tray, three widget sizes, opacity and pinning.
- Separate details and 10-minute in-memory power history.
- Approximate discharge runtime with smoothed load; unavailable data stays blank.
- Release Bluetooth for the phone without closing the application.
- Explicit stale-data state and readback verification after setting commands.
- Author feedback from the `?` button or tray menu: opens a public GitHub issue
  draft for bugs or suggestions. Nothing is submitted automatically; logs,
  Bluetooth addresses and serial numbers are never attached automatically.

## Run from source

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe widget.py
```

Open `···` → select station → scan. Close the station connection in the phone
app first. No station address is shipped with this project.

`↗` opens details. `Телефон` releases Bluetooth, `Повернути` reconnects.
`×` hides to the tray. Right-click / `···` changes size, opacity and position.
Exit from the tray menu to quit.

Settings and rotating diagnostic logs are created beside the executable.
Keep the application in a writable directory. Do not upload your settings,
logs, Bluetooth addresses or station serial number to public issues.

## Build

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller==6.22.3
.\build.ps1
.\.venv\Scripts\python.exe build_portable.py
```

Folder executable: `dist/BluettiWidget/BluettiWidget.exe`.
Single-file executable: `portable/BluettiWidget.exe`. Initial startup includes
temporary extraction. Release builds must start with no personal settings.

## Test

```powershell
.\.venv\Scripts\python.exe check_widget.py
.\.venv\Scripts\python.exe test_models.py
.\.venv\Scripts\python.exe test_feedback.py
.\.venv\Scripts\python.exe widget.py --demo
```

Demo values are synthetic. Hardware checks are separate and read-only;
see `CONTRIBUTING.md` before reporting a model as tested.

## Runtime estimates

The estimate uses the model capacity, reported state of charge, 90% depth of
discharge, 85% conversion efficiency and 15 W self-consumption, following
[BLUETTI's example](https://www.bluettipower.com/products/ac180p/).
It averages recent output readings and rounds down to five minutes. It is
not a BMS prediction or a guarantee. No estimate is shown with external input,
zero load or stale data. AC180 estimates are experimental.

## Roadmap

1. Collect AC180P firmware and reconnect reports from more owners.
2. Validate AC180 monitoring on hardware before enabling controls.
3. English/Ukrainian UI selection and installable Windows releases.
4. Add BLUETTI profiles with register evidence and tests.
5. Add separate brand adapters without changing the UI's telemetry contract.

Unofficial project; not affiliated with BLUETTI. See `THIRD_PARTY.md` for
dependency licenses. No official binary release has been published yet.
