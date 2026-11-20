# Contributing

For a new model, open a model request with model name, firmware version,
Windows version, adapter type, and which readings match the official app.
Remove Bluetooth addresses, serial numbers and personal paths from evidence.

Add an explicit profile in `models.py`. Confirm register addresses from an
upstream implementation or captured protocol evidence. Unknown models must
never inherit another model's write registers by default. Start read-only.

Include tests for model detection, telemetry parsing and unavailable fields.
Runtime estimates require model-specific capacity and documented assumptions.
Hardware reports should distinguish monitoring, reconnects and actual control
tests. Do not test a power-off command with a critical load attached.

Run the offline tests before submitting a pull request. Screenshots should
come from demo mode or have personal identifiers removed.
