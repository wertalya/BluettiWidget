"""Перевірки пауз між пакетами, кешу налаштувань і повторного підключення."""
import asyncio
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import get_profile
from app.powerlink import BluetoothWorker, LiveSession
from bluetti_bt_lib.registers.DeviceRegister import modbus_crc


class ConnectionTests(unittest.TestCase):
    def test_core_is_polled_each_cycle_controls_are_cached_and_force_refreshes(self):
        async def exercise():
            session = LiveSession(AsyncMock())
            device = MagicMock()
            device.parse.side_effect = lambda address, body: {str(address): body}
            plan = ((102, 1), (140, 8), (2011, 2), (2020, 1))
            slow = plan[2:]
            with patch.object(session, 'request', AsyncMock(return_value=b'data')) as request:
                first = await session.read(device, plan, slow_blocks=slow)
                request.reset_mock()
                self.assertEqual(await session.read(device, plan, slow_blocks=slow), first)
                self.assertEqual([call.args for call in request.await_args_list], list(plan[:2]))
                request.reset_mock()
                await session.read(device, plan, slow_blocks=slow, force_controls=True)
                self.assertEqual([call.args for call in request.await_args_list], list(plan))
                request.reset_mock()
                with patch('app.powerlink.time.monotonic', return_value=time.monotonic() + 6):
                    await session.read(device, plan, slow_blocks=slow)
                self.assertEqual([call.args for call in request.await_args_list], list(plan))
            self.assertEqual(LiveSession(AsyncMock()).cached_blocks, {})
        asyncio.run(exercise())

    def test_requests_wait_between_frames_and_validate_modbus_reply(self):
        async def exercise():
            client = AsyncMock()
            session = LiveSession(client)
            session.write_with_response = False
            stamps = []
            async def reply(*args, **kwargs):
                stamps.append(time.monotonic())
                body = bytes([1, 3, 2, 0, 50])
                session.notification(None, body + modbus_crc(body).to_bytes(2, 'little'))
            client.write_gatt_char.side_effect = reply
            with patch('app.powerlink.REQUEST_GAP', .03):
                await session.request(102, 1)
                await session.request(102, 1)
            self.assertGreaterEqual(stamps[1] - stamps[0], .025)
            self.assertFalse(client.write_gatt_char.await_args.kwargs['response'])
            self.assertIsNone(session.pending)
        asyncio.run(exercise())

    def test_missing_reply_times_out_without_claiming_success(self):
        async def exercise():
            client = AsyncMock()
            session = LiveSession(client)
            with patch('app.powerlink.REQUEST_TIMEOUT', .01):
                with self.assertLogs(level='WARNING') as logs, self.assertRaises(TimeoutError):
                    await session.request(102, 1)
            self.assertIn('stage=station_reply', logs.output[0])
            self.assertIsNone(session.pending)
        asyncio.run(exercise())

    def test_cached_device_is_reused_on_reconnect_but_expired_cache_scans(self):
        async def exercise():
            worker = BluetoothWorker()
            worker.address = 'test'
            device = type('Device', (), {'address': 'test'})()
            found = {'test': (device, None)}
            worker.cache_scan(found)
            with patch('app.powerlink.BleakScanner.discover', AsyncMock(return_value=found)) as scan:
                self.assertIs(await worker.find_device(), device)
                self.assertIs(await worker.find_device(), device)
                scan.assert_not_awaited()
                worker.scan_time -= 61
                self.assertIs(await worker.find_device(), device)
                scan.assert_awaited_once()
        asyncio.run(exercise())

    def test_open_uses_supported_write_mode_and_falls_back_to_acknowledged_write(self):
        async def exercise():
            for properties, response in ((['write-without-response', 'write'], False), (['write'], True)):
                worker = BluetoothWorker()
                client = MagicMock()
                client.connect = AsyncMock()
                client.start_notify = AsyncMock()
                client.services.get_characteristic.return_value.properties = properties
                with patch('app.powerlink.BleakClient', return_value=client):
                    session = await worker.open_live(object(), False)
                self.assertEqual(session.write_with_response, response)
        asyncio.run(exercise())

    def test_setting_write_always_forces_fresh_control_readback(self):
        async def exercise():
            worker = BluetoothWorker()
            worker.last_read = time.monotonic()
            live = LiveSession(AsyncMock())
            with patch.object(worker, 'ensure_live', AsyncMock(return_value=live)), \
                 patch.object(worker, 'read', AsyncMock(return_value={'ctrl_ac': True})) as read, \
                 patch('app.powerlink.asyncio.sleep', AsyncMock()):
                await worker.write('ctrl_ac', True)
            read.assert_awaited_once_with(force_controls=True)
        asyncio.run(exercise())


if __name__ == '__main__':
    unittest.main()
