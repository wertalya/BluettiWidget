# Contributing

Open a [model report](https://github.com/wertalya/BluettiWidget/issues/new?template=model-request.yml)
with the model name, firmware version,
Windows version, adapter type, and which readings match the official app.
Remove Bluetooth addresses, serial numbers and personal paths from evidence.
For a capacity contribution, include the model key and capacity in Wh, plus a
public reference where available. Share only the model setting from your
configuration. Reports inform reviewed profile changes.

Models with a charge field in the pinned BLE library receive a read-only
profile automatically. Add an override in `models.py` when capacity, field
names or register batches differ. Confirm register addresses against the
upstream mapping or captured protocol evidence. Unknown models must
never inherit another model's write registers by default. Start read-only.

Include tests for model detection, telemetry parsing and unavailable fields.
Runtime estimates require model-specific capacity and documented assumptions.
Hardware reports should distinguish monitoring, reconnects and actual control
tests. Do not test a power-off command with a critical load attached.

Run the offline tests before submitting a pull request. Screenshots should
come from demo mode or have personal identifiers removed.
