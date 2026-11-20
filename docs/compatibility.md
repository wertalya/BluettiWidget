# BLUETTI compatibility

BluettiWidget recognizes **29 BLUETTI models** from the pinned BLE protocol
library. Compatibility depends on firmware, the Windows Bluetooth adapter,
and the fields the station exposes.

| Status | Models |
| --- | --- |
| Monitoring checked on hardware | AC180P |
| Experimental, read-only | AC2A, AC2P, AC50B, AC60, AC60P, AC70, AC70P, AC180, AC180T, AC200L, AC200M, AC200PL, AC300, AC500, AP300, EB3A, EL10, EL100V2, EL30V2, EP500, EP500P, EP600, EP760, EP800, EP2000, Handsfree 1, PR30V2, PR100V2 |

The AC180P exposes AC/DC and charging-mode controls on unencrypted BLE.
Hardware validation in this project covers monitoring and reconnection.
Encrypted BLE runs read-only. Missing input or output readings are shown as
a dash. The detailed view shows the fields the station actually reports.

## How models are detected

Each advertised name is matched against a known model and its optional numeric
suffix. The app uses that model's own register map from `bluetti-bt-lib`.
A library model is discoverable when it exposes state of charge. Additional
profiles inherit read-only defaults. Unknown names need a verified protocol
map before they can be supported.

## Capacity and new models

AC180P and AC180 have defaults of 1440 Wh and 1152 Wh. For any detected model,
add its installed battery capacity under `[capacity_wh]` in local
`settings.ini` and restart. See [settings.example.ini](../settings.example.ini).
For systems with expansion batteries, use the total installed capacity.
The runtime estimate needs a known capacity, reported load and no incoming
power.

For a model already in the protocol library, use an override in `models.py`
only when you need to specify capacity, field aliases or register batches.
For a model outside the library, add or verify its BLE mapping first.
Other manufacturers can be integrated with a separate transport and parser
that produce the same telemetry fields. See
[CONTRIBUTING.md](../CONTRIBUTING.md) for the testing and reporting process.
