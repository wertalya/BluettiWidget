"""Offline checks: parse telemetry, render states, prevent unsafe/stale writes."""
import asyncio
import os
import time
import unittest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from bleak.exc import BleakError
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QCoreApplication, QEvent
from bluetti_bt_lib.enums import ChargingMode
from powerlink import BluetoothWorker, InvalidFrame, LiveSession, RegisterRejected, normalize
from bluetti_bt_lib.registers import ReadableRegisters
from bluetti_bt_lib.registers.DeviceRegister import modbus_crc
from widget import Panel, STYLE, SIZES, describe_state
from runtime_estimate import RuntimeEstimator, runtime_hours, format_runtime


SAMPLE = {"total_battery_percent": 70, "ac_input_power": 0, "dc_input_power": 0,
          "ac_output_power": 145, "dc_output_power": 0, "ctrl_ac": True,
          "ctrl_dc": True, "ctrl_charging_mode": ChargingMode.TURBO}


class Checks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyleSheet(STYLE)
        # Keep unit tests independent of Explorer's notification-area IPC.
        # The actual tray is checked with the packaged application separately.
        cls.tray_patch = patch('widget.QSystemTrayIcon')
        cls.tray_patch.start()

    @classmethod
    def tearDownClass(cls):
        cls.tray_patch.stop()

    def test_real_telemetry_shape_and_staleness(self):
        with tempfile.TemporaryDirectory() as tmp:
            panel = Panel(start_worker=False,settings_path=Path(tmp)/'settings.ini')
            panel.update_reading(normalize(SAMPLE))
            panel.open_details()
            self.assertEqual(panel.metrics['ac_output_power'].text(),'145 Вт')
            self.assertEqual(panel.mode.currentData(),'TURBO')
            self.assertEqual(panel.cluster.targets,[0,145])
            self.assertTrue(panel.switches['ctrl_ac'].isEnabled())
            self.assertIn('Увімкн.',panel.switches['ctrl_ac'].text())
            for name,size in SIZES.items():
                panel.apply_size(name)
                self.assertEqual((panel.width(),panel.height()),size)
            panel.last_update=time.monotonic()-8
            panel.check_age()
            self.assertFalse(panel.switches['ctrl_ac'].isEnabled())
            self.assertTrue(panel.cluster.stale)
            panel.send_command('ctrl_dc',False)
            self.assertTrue(panel.worker.commands.empty())
            panel.update_reading({'total_battery_percent':70})
            self.assertEqual(panel.metrics['ac_output_power'].text(),'— Вт')
            self.assertFalse(panel.mode.isEnabled())
            self.dispose(panel)

    def dispose(self,panel):
        panel.shutdown()
        panel.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_handoff_blocks_controls_and_stale_readings(self):
        with tempfile.TemporaryDirectory() as tmp:
            panel=Panel(start_worker=False,settings_path=Path(tmp)/'settings.ini')
            panel.update_reading(normalize(SAMPLE))
            panel.toggle_bluetooth()
            self.assertEqual(panel.worker.commands.get_nowait(),('pause',None))
            self.assertFalse(panel.switches['ctrl_ac'].isEnabled())
            panel.update_reading({**normalize(SAMPLE),'total_battery_percent':99})
            self.assertEqual(panel.data['total_battery_percent'],70)
            panel.on_paused(True)
            self.assertIn('вільний',panel.status.text())
            self.assertFalse(panel.fresh())
            panel.send_command('ctrl_ac',True)
            self.assertTrue(panel.worker.commands.empty())
            panel.toggle_bluetooth()
            self.assertEqual(panel.worker.commands.get_nowait(),('resume',None))
            panel.on_paused(False)
            panel.update_reading(normalize(SAMPLE))
            self.assertTrue(panel.fresh())
            self.dispose(panel)

    def test_saved_preferences_and_history_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'settings.ini'
            panel=Panel(start_worker=False,settings_path=path)
            panel.apply_size('S'); panel.set_position_locked(True); panel.set_opacity(80)
            for stamp in range(1000): panel.history.add(stamp,stamp,12)
            self.assertLessEqual(len(panel.history.samples),601)
            self.dispose(panel)
            panel=Panel(start_worker=False,settings_path=path)
            self.assertEqual(panel.size_name,'S')
            self.assertTrue(panel.position_locked)
            self.assertEqual(panel.opacity,80)
            self.dispose(panel)

    def test_status_does_not_call_bypass_battery_charging(self):
        data=normalize(SAMPLE)
        self.assertEqual(describe_state(data),'Живить пристрої')
        self.assertEqual(describe_state({**data,'ac_input_power':500}),'Вхід і навантаження')
        self.assertEqual(describe_state({**data,'ac_input_power':500,'ac_output_power':0}),'Заряджається')

    def test_worker_pause_and_resume_without_automatic_polls(self):
        async def exercise():
            worker=BluetoothWorker(); worker.address='fake'
            with patch.object(worker,'read',AsyncMock()), patch.object(worker,'disconnect',AsyncMock()):
                worker.submit('pause')
                task=asyncio.create_task(worker.work())
                await asyncio.sleep(.35)
                self.assertTrue(worker.paused)
                worker.read.assert_not_awaited()
                worker.submit('resume')
                await asyncio.sleep(.35)
                self.assertFalse(worker.paused)
                worker.read.assert_awaited_once()
                worker.stop()
                await task
        asyncio.run(exercise())

    def test_resume_after_long_clock_gap_discards_old_connection(self):
        async def exercise():
            worker=BluetoothWorker(); worker.address='fake'; worker.live=object()
            stopped=[False]
            async def disconnect():
                worker.live=None
                return True
            async def read():
                stopped[0]=True
            with patch.object(worker,'disconnect',AsyncMock(side_effect=disconnect)), \
                 patch.object(worker,'read',AsyncMock(side_effect=read)), \
                 patch.object(worker,'isInterruptionRequested',side_effect=lambda:stopped[0]):
                await worker.work_loop(0,0,time.monotonic()-10)
                worker.disconnect.assert_awaited_once()
                worker.read.assert_awaited_once()
        asyncio.run(exercise())

    def test_cancel_during_disconnect_finishes_disposal(self):
        async def exercise():
            worker=BluetoothWorker(); client=AsyncMock(); client.is_connected=True
            disposed=asyncio.Event()
            async def dispose():
                await asyncio.sleep(.03)
                client.is_connected=False
                disposed.set()
            client.disconnect.side_effect=dispose
            worker.live=LiveSession(client)
            task=asyncio.create_task(worker.disconnect())
            await asyncio.sleep(.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(disposed.is_set())
            self.assertIsNone(worker.live)
        asyncio.run(exercise())

    def test_picker_persists_a_station_only_after_telemetry(self):
        with tempfile.TemporaryDirectory() as tmp:
            panel = Panel(start_worker=False, settings_path=Path(tmp) / 'settings.ini')
            panel.open_picker()
            self.assertEqual(panel.worker.commands.get_nowait(), ('scan', None))
            station = {'name': 'EB3A123', 'model': 'EB3A', 'address': 'test', 'encrypted': False}
            panel.picker.found([station])
            panel.picker.choose()
            self.assertEqual(panel.worker.commands.get_nowait(), ('select', station))
            panel.on_selected(station)
            self.assertIsNone(panel.settings.value('address'))
            self.assertTrue(panel.picker.isVisible())
            panel.update_reading({'total_battery_percent': 42})
            self.assertEqual(panel.settings.value('address'), 'test')
            self.assertFalse(panel.picker.isVisible())
            self.assertEqual(panel.cluster.runtime_text, '—')
            self.assertFalse(panel.windowIcon().isNull())
            self.dispose(panel)

    def test_new_selection_uses_scan_device_without_a_second_scan(self):
        async def exercise():
            worker = BluetoothWorker()
            worker.address = 'TEST'
            device = type('Device', (), {'address': 'test'})()
            worker.cache_scan({'test': (device, None)})
            with patch('powerlink.BleakScanner.discover', AsyncMock()) as scan:
                self.assertIs(await worker.find_device(), device)
                scan.assert_not_awaited()
        asyncio.run(exercise())

    def test_winrt_notification_failure_refreshes_services(self):
        async def exercise():
            worker = BluetoothWorker()
            station = object()
            session = object()
            with patch('powerlink.sys.platform', 'win32'), \
                 patch.object(worker, 'find_device', AsyncMock(return_value=station)), \
                 patch.object(worker, 'disconnect', AsyncMock(return_value=True)), \
                 patch.object(worker, 'open_live', AsyncMock(side_effect=[
                     BleakError('disconnected'), session, session,
                 ])) as connect:
                self.assertIs(await worker.ensure_live(), session)
                self.assertTrue(worker.prefer_uncached)
                self.assertIs(await worker.ensure_live(), session)
                self.assertEqual([call.args for call in connect.await_args_list],
                                 [(station, False), (station, True), (station, True)])
        asyncio.run(exercise())

    def test_optional_register_rejection_and_corrupt_frame_recovery(self):
        async def exercise():
            worker = BluetoothWorker()
            session = LiveSession(AsyncMock())
            with patch.object(session, 'request', AsyncMock(side_effect=[
                InvalidFrame(), b'\x00\x32', RegisterRejected(), b'\x00\x33',
            ])) as request:
                plan = ((102, 1), (140, 1))
                self.assertEqual(normalize(await session.read(worker.device, plan)),
                                 {'total_battery_percent': 50})
                self.assertEqual(normalize(await session.read(worker.device, plan)),
                                 {'total_battery_percent': 51})
                self.assertEqual(request.await_count, 4)
        asyncio.run(exercise())

    def test_normalization_rejects_bad_soc(self):
        self.assertEqual(normalize(SAMPLE)["ctrl_charging_mode"], "TURBO")
        for value in (None, -1, 101, True, "73"):
            with self.assertRaises(ValueError):
                normalize({"total_battery_percent": value})

    def test_runtime_matches_published_example_and_current_load(self):
        self.assertAlmostEqual(runtime_hours(100,40),20.02909,places=4)
        self.assertEqual(format_runtime(runtime_hours(81,340)),'≈ 2 год 30 хв')
        self.assertEqual(format_runtime(.02),'≈ <5 хв')
        for soc,load in [(None,40),(101,40),(-1,40),(True,40),(50,0),(50,float('nan'))]:
            self.assertIsNone(runtime_hours(soc,load))

    def test_runtime_averaging_gaps_and_external_power(self):
        estimator=RuntimeEstimator()
        estimator.update(81,0,300,0)
        estimator.update(81,0,400,1)
        self.assertEqual(estimator.average_w,350)
        estimator.update(81,0,500,30)
        self.assertEqual(estimator.average_w,500)
        self.assertIsNone(estimator.update(81,100,500,31))
        self.assertIsNone(estimator.average_w)
        self.assertIsNone(estimator.update(81,float('nan'),500,32))

    def test_write_requires_fresh_data_and_unencrypted_device(self):
        worker = BluetoothWorker()
        with self.assertRaises(RuntimeError):
            asyncio.run(worker.write("ctrl_ac", False))
        worker.encrypted = True
        with self.assertRaises(RuntimeError):
            asyncio.run(worker.write("ctrl_dc", True))

    def test_write_must_be_confirmed_by_readback(self):
        async def exercise():
            worker = BluetoothWorker()
            worker.address = "00:11:22:33:44:55"
            worker.last_read = time.monotonic()
            client = AsyncMock()
            live = LiveSession(client)
            with patch.object(worker, "ensure_live", AsyncMock(return_value=live)), \
                 patch("powerlink.asyncio.sleep", AsyncMock()), \
                 patch.object(worker, "read", AsyncMock(return_value={"ctrl_ac": True})):
                with self.assertRaisesRegex(RuntimeError, "не підтвердила"):
                    await worker.write("ctrl_ac", False)
                client.write_gatt_char.assert_awaited_once()
                await worker.write("ctrl_ac", True)
        asyncio.run(exercise())

    def test_fragmented_response_and_crc(self):
        async def exercise():
            session = LiveSession(AsyncMock())
            session.register = ReadableRegisters(102, 1)
            session.pending = asyncio.get_running_loop().create_future()
            body = bytes([1, 3, 2, 0, 66])
            frame = body + modbus_crc(body).to_bytes(2, 'little')
            session.notification(None, frame[:4])
            self.assertFalse(session.pending.done())
            session.notification(None, frame[4:])
            self.assertEqual(await session.pending, frame)
            session.buffer.clear()
            session.pending=asyncio.get_running_loop().create_future()
            echo_body=bytes([1,6,7,219,0,1])
            echo=echo_body+modbus_crc(echo_body).to_bytes(2,'little')
            session.notification(None,echo+frame)
            self.assertEqual(await session.pending,frame)
            session.buffer.clear()
            session.pending = asyncio.get_running_loop().create_future()
            session.notification(None, frame[:-1] + b'\x00')
            with self.assertRaises(ValueError):
                await session.pending
        asyncio.run(exercise())


if __name__ == "__main__":
    unittest.main()
