"""Explicit BLUETTI profiles. Unknown models never inherit another model's registers."""
from dataclasses import dataclass
import re
from bluetti_bt_lib.devices.ac180 import AC180
from bluetti_bt_lib.devices.ac180p import AC180P

@dataclass(frozen=True)
class StationProfile:
    model: str
    capacity_wh: int
    device_factory: type
    controls: bool
    tested: bool

PROFILES = {
    'AC180P': StationProfile('AC180P',1440,AC180P,True,True),
    'AC180': StationProfile('AC180',1152,AC180,False,False),
}

def detect_profile(name):
    match = re.fullmatch(r'(AC180P|AC180)[0-9]*',name.strip().upper())
    return PROFILES.get(match[1]) if match else None

def get_profile(model):
    if model not in PROFILES:
        raise ValueError('Unsupported station model; add a verified model profile first')
    return PROFILES[model]
