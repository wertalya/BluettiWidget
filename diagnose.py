"""Read-only discovery and telemetry check. Never sends setting commands."""
import asyncio
import json
from bleak import BleakClient, BleakScanner
from bluetti_bt_lib import DeviceReader, DeviceReaderConfig
from bluetti_bt_lib.devices.ac180p import AC180P


async def main():
    found = await BleakScanner.discover(timeout=8, return_adv=True)
    candidates = [(d, a) for d, a in found.values()
                  if (a.local_name or d.name or "").startswith("AC180P")]
    print("AC180P devices:", len(candidates))
    if len(candidates) != 1:
        return
    device, ad = candidates[0]
    encrypted = b"BLUETTE" in b"".join(ad.manufacturer_data.values())
    print("Encrypted:", encrypted)
    async with BleakClient(device, timeout=12) as client:
        reader = DeviceReader(device.address, AC180P(), asyncio.get_running_loop().create_future,
            DeviceReaderConfig(timeout=15, use_encryption=encrypted),
            lock=asyncio.Lock(), ble_client=client)
        data = await reader.read()
    if data:
        data.pop("device_sn", None)
    print(json.dumps(data, default=str, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
