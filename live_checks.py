"""Read-only integration check: streaming, release, pause and reconnect."""
import asyncio
import json
import sys
import time
from powerlink import BluetoothWorker


async def wait_for(predicate, timeout=50):
    end = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > end:
            raise TimeoutError('Live check did not reach the expected state')
        await asyncio.sleep(.1)


async def main():
    worker = BluetoothWorker()
    samples = []
    pause_acks = []
    worker.reading.connect(lambda data: samples.append((time.monotonic(), data)))
    worker.paused_changed.connect(pause_acks.append)
    task = asyncio.create_task(worker.work())
    try:
        worker.submit('select', {'address': sys.argv[1], 'encrypted': False})
        await wait_for(lambda: len(samples) >= 4)
        client = worker.live.client
        worker.submit('pause')
        await wait_for(lambda: pause_acks and pause_acks[-1] is True)
        assert not client.is_connected, 'Bluetooth connection was not released'
        count = len(samples)
        await asyncio.sleep(2)
        assert len(samples) == count, 'Polling continued during phone handoff'
        resumed = time.monotonic()
        worker.submit('resume')
        await wait_for(lambda: len(samples) >= count + 3)
        print(json.dumps({
            'samples': len(samples),
            'steady_intervals': [round(samples[i][0] - samples[i-1][0], 3) for i in (1,2,3)],
            'bluetooth_released': not client.is_connected,
            'paused_polling': False,
            'resume_seconds': round(samples[count][0] - resumed, 3),
            'gatt_ack': worker.live.write_with_response,
            'latest': {k:v for k,v in samples[-1][1].items() if k != 'device_sn'},
        }, ensure_ascii=False, default=str), flush=True)
    finally:
        worker.stop()
        await task


if __name__ == '__main__':
    asyncio.run(main())
