"""Model profiles and register plans for the BLUETTI telemetry the UI uses."""
from dataclasses import dataclass
import re

from bluetti_bt_lib.devices import DEVICES

SOC = 'total_battery_percent'
POWER_FIELDS = ('ac_input_power', 'dc_input_power', 'ac_output_power', 'dc_output_power')
CONTROL_FIELDS = ('ctrl_ac', 'ctrl_dc', 'ctrl_charging_mode')


@dataclass(frozen=True)
class StationProfile:
    model: str
    capacity_wh: int | None = None
    controls: bool = False
    tested: bool = False
    # Tuples of (canonical UI field, field used by the upstream parser).
    aliases: tuple[tuple[str, str], ...] = ()
    # A verified profile can override automatic batching.
    read_blocks: tuple[tuple[int, int], ...] = ()

    @property
    def device_factory(self):
        return DEVICES[self.model]

    def read_plan(self, device):
        aliases = dict(self.aliases)
        fields = {field.name: field for field in device.fields}
        soc_field = fields[aliases.get(SOC, SOC)]
        required = (soc_field.address, soc_field.size)
        if self.read_blocks:
            return (required, *self.read_blocks)

        names = POWER_FIELDS + (CONTROL_FIELDS if self.controls else ())
        spans = sorted((field.address, field.address + field.size)
                       for name in names if (field := fields.get(aliases.get(name, name))))
        blocks = []
        for start, end in spans:
            # Merge adjacent fields only so a firmware can reject an optional
            # register without making unrelated telemetry unavailable.
            if blocks and start <= blocks[-1][1] and end - blocks[-1][0] <= 8:
                blocks[-1] = (blocks[-1][0], max(end, blocks[-1][1]))
            else:
                blocks.append((start, end))
        return (required, *((start, end - start) for start, end in blocks))


# Register maps come from the pinned BLE library. A model needs a charge
# field to appear in discovery. Only reviewed overrides can enable writes.
PROFILES = {
    name: StationProfile(name)
    for name, factory in DEVICES.items()
    if any(field.name == SOC for field in factory().fields)
}
for profile in (
    StationProfile('AC180P', 1440, controls=True, tested=True,
                   read_blocks=((140, 8), (2011, 2), (2020, 1))),
    StationProfile('AC180', 1152, read_blocks=((140, 8),)),
):
    PROFILES[profile.model] = profile

MODEL_NAMES = {name.upper(): name for name in PROFILES}


def detect_profile(name):
    name = name.strip().upper()
    for prefix, model in MODEL_NAMES.items():
        if re.fullmatch(re.escape(prefix) + r'[0-9]*', name):
            return PROFILES[model]
    return None


def get_profile(model):
    if model not in PROFILES:
        raise ValueError('Unsupported station model; add a verified model profile first')
    return PROFILES[model]
