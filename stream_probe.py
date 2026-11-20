"""Read-only measurement of repeated telemetry on one BLE connection."""
import asyncio
import json
import sys
import time
from powerlink import BluetoothWorker

async def main():
    worker = BluetoothWorker()
    worker.address = sys.argv[1]
    stamps = []
    client = None
    try:
        for i in range(8):
            started = time.monotonic()
            for attempt in range(3):
                try:
                    data = await worker.read()
                    break
                except Exception:
                    await worker.disconnect()
                    if attempt == 2 or client is not None:
                        raise
                    await asyncio.sleep(2)
            if client is None:
                client = worker.live.client
            assert worker.live.client is client, 'Connection was replaced'
            stamps.append(time.monotonic())
            print(json.dumps({'sample': i + 1, 'soc': data['total_battery_percent'],
                'output_w': data['ac_output_power'] + data['dc_output_power'],
                'read_seconds': round(stamps[-1] - started, 3)}, ensure_ascii=False), flush=True)
            await asyncio.sleep(max(.1, 1 - (time.monotonic() - started)))
        print('Intervals:', [round(b-a, 3) for a,b in zip(stamps, stamps[1:])], flush=True)
        print('Single connection: OK', flush=True)
    finally:
        await worker.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
