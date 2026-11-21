"""BLUETTI BLE worker. All Bluetooth operations stay off the UI thread."""
import asyncio
from copy import copy
from decimal import Decimal
import logging
import math
import queue
import sys
import time

from PySide6.QtCore import QThread, Signal
from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
from bluetti_bt_lib import DeviceReader, DeviceReaderConfig
from bluetti_bt_lib.const import WRITE_UUID, NOTIFY_UUID
from bluetti_bt_lib.registers import ReadableRegisters
from .models import POWER_FIELDS, SOC, detect_profile, get_profile

WRITABLE = {"ctrl_ac", "ctrl_dc", "ctrl_charging_mode"}


class RegisterRejected(ValueError):
    pass


class InvalidFrame(ValueError):
    pass


class LiveSession:
    """One BLE connection, sequential requests and fragmented reply assembly."""
    def __init__(self, client):
        self.client = client
        self.pending = None
        self.buffer = bytearray()
        self.register = None
        self.write_with_response = True
        self.unsupported = set()

    def notification(self, sender, data):
        if self.pending is None or self.pending.done():
            return
        self.buffer.extend(data)
        # Ignore acknowledgements of an earlier settings write.
        while len(self.buffer) >= 3 and self.buffer[1] == 6:
            if len(self.buffer) < 8:
                return
            del self.buffer[:8]
        if len(self.buffer) < 3:
            return
        expected = 5 if self.buffer[1] & 0x80 else self.buffer[2] + 5
        if len(self.buffer) < expected:
            return
        frame = bytes(self.buffer[:expected])
        if not self.register.is_valid_response(frame):
            self.pending.set_exception(InvalidFrame("Пошкоджена відповідь Bluetooth"))
        elif self.register.is_exception_response(frame):
            self.pending.set_exception(RegisterRejected("Станція відхилила запит даних"))
        elif frame[0:2] != b'\x01\x03' or len(frame) != self.register.response_size():
            self.pending.set_exception(ValueError("Неочікувана відповідь станції"))
        else:
            self.pending.set_result(frame)

    def disconnected(self, _client):
        if self.pending is not None and not self.pending.done():
            self.pending.set_exception(ConnectionError("Bluetooth-з’єднання втрачено"))

    async def request(self, address, count):
        self.register = ReadableRegisters(address, count)
        self.buffer.clear()
        self.pending = asyncio.get_running_loop().create_future()
        try:
            async with asyncio.timeout(3):
                await self.client.write_gatt_char(
                    WRITE_UUID, bytes(self.register), response=self.write_with_response
                )
                frame = await self.pending
            return self.register.parse_response(frame)
        finally:
            # A disconnect can arrive before write_gatt_char itself fails.
            if self.pending.done() and not self.pending.cancelled():
                self.pending.exception()
            self.pending.cancel()
            self.pending = None

    async def read(self, device, plan):
        data = {}
        for index, block in enumerate(plan):
            if block in self.unsupported:
                continue
            try:
                try:
                    body = await self.request(*block)
                except InvalidFrame:
                    # The full response was received. One retry is safe here.
                    body = await self.request(*block)
            except RegisterRejected:
                if index == 0:
                    raise
                self.unsupported.add(block)
                continue
            data.update(device.parse(block[0], body))
        return data


def normalize(data, aliases=()):
    result = {}
    for key, value in data.items():
        key = getattr(key, "value", key)
        if key == "device_sn":
            continue
        result[key] = getattr(value, "name", value)
    for canonical, source in aliases:
        if source in result:
            result[canonical] = result[source]
    soc = result.get(SOC)
    if type(soc) is not int or not 0 <= soc <= 100:
        raise ValueError("Станція не повернула коректний рівень заряду")
    for field in POWER_FIELDS:
        value = result.pop(field, None)
        if isinstance(value, Decimal):
            value = float(value)
        if type(value) in (int, float) and math.isfinite(value) and value >= 0:
            result[field] = value
    return result


class BluetoothWorker(QThread):
    devices = Signal(list)
    reading = Signal(dict)
    scan_failed = Signal(str)
    retrying = Signal(str)
    status = Signal(str)
    failure = Signal(str)
    selected = Signal(dict)
    command_done = Signal(bool, str)
    paused_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self.commands = queue.Queue()
        self.address = ""
        self.encrypted = False
        self.last_read = 0.0
        self.profile = get_profile('AC180P')
        self.device = self.profile.device_factory()
        self.plan = self.profile.read_plan(self.device)
        self.discovered = {}
        self.scan_time = 0.0
        self.prefer_uncached = False
        self.live = None
        self.paused = False
        self.loop = None
        self.task = None

    def stop(self):
        self.requestInterruption()
        if self.loop and self.task:
            try:
                self.loop.call_soon_threadsafe(self.task.cancel)
            except RuntimeError:
                pass

    async def disconnect(self):
        live, self.live = self.live, None
        if live:
            cleanup = asyncio.create_task(live.client.disconnect())
            try:
                await asyncio.wait_for(asyncio.shield(cleanup), timeout=5)
                return not live.client.is_connected
            except asyncio.CancelledError:
                # Finish BLE disposal even when the UI quits during handoff.
                try:
                    await asyncio.wait_for(cleanup, timeout=5)
                finally:
                    raise
            except Exception:
                cleanup.cancel()
                logging.warning("Bluetooth disconnect failed")
                return False
        return True

    async def find_device(self):
        address = self.address.casefold()
        if time.monotonic() - self.scan_time < 60:
            device = self.discovered.pop(address, None)
            if device is not None:
                return device
        self.status.emit("Шукаю станцію…")
        found = await BleakScanner.discover(timeout=8, return_adv=True)
        self.cache_scan(found)
        device = self.discovered.pop(address, None)
        if device is None:
            raise RuntimeError("Станція недоступна. Перевір відстань і з’єднання на телефоні.")
        return device

    def cache_scan(self, found):
        self.discovered = {device.address.casefold(): device for device, _ in found.values()}
        self.scan_time = time.monotonic()

    async def ensure_live(self):
        if self.live and self.live.client.is_connected:
            return self.live
        await self.disconnect()
        device = await self.find_device()
        self.status.emit("Станцію знайдено · підключаюся…")
        # WinRT's cached services can connect successfully but fail when the
        # client registers notifications. Keep the last working mode per target.
        if sys.platform != "win32":
            return await self.open_live(device, uncached=False)
        try:
            return await self.open_live(device, self.prefer_uncached)
        except (BleakError, TimeoutError, OSError):
            if not await self.disconnect():
                raise
            self.status.emit("Повторюю підключення…")
            live = await self.open_live(device, not self.prefer_uncached)
            self.prefer_uncached = not self.prefer_uncached
            return live

    async def open_live(self, device, uncached):
        def on_disconnected(client):
            if self.live and self.live.client is client:
                self.live.disconnected(client)

        options = {"winrt": {"use_cached_services": False}} if uncached else {}
        client = BleakClient(device, timeout=12, disconnected_callback=on_disconnected, **options)
        self.live = LiveSession(client)
        async with asyncio.timeout(12):
            await client.connect()
            characteristic = client.services.get_characteristic(WRITE_UUID)
            if characteristic is None:
                raise BleakError("У станції немає очікуваного Bluetooth-сервісу")
            self.live.write_with_response = 'write' in characteristic.properties
            await client.start_notify(NOTIFY_UUID, self.live.notification)
        self.status.emit("Отримую живі показники…")
        return self.live

    def submit(self, action, payload=None):
        self.commands.put((action, payload))

    def run(self):
        asyncio.run(self.work())

    async def scan(self):
        found = await BleakScanner.discover(timeout=8, return_adv=True)
        self.cache_scan(found)
        devices = []
        for dev, adv in found.values():
            name = adv.local_name or dev.name or ""
            profile = detect_profile(name)
            if profile is None:
                continue
            marker = b"".join(adv.manufacturer_data.values())
            devices.append({"name": name, "model":profile.model, "address": dev.address,
                            "encrypted": b"BLUETTE" in marker})
        self.devices.emit(sorted(devices, key=lambda item: item["name"]))

    async def read(self):
        loop = asyncio.get_running_loop()
        if not self.encrypted:
            async with asyncio.timeout(40):
                live = await self.ensure_live()
                data = await live.read(self.device, self.plan)
            data = normalize(data, self.profile.aliases)
            self.last_read = time.monotonic()
            self.reading.emit(data)
            self.status.emit("Живі дані · оновлення щосекунди")
            return data
        # Use the discovered device object directly. Avoid a second short scan
        # in the library, which can miss intermittent Windows advertisements.
        async with asyncio.timeout(30):
            device = await self.find_device()
            async with BleakClient(device, timeout=12) as client:
                device_map = self.device
                if device_map.max_packs:
                    # The library still selects every pack when only_registers
                    # is passed. This widget requests station-level data only.
                    device_map = copy(device_map)
                    device_map.max_packs = 0
                reader = DeviceReader(self.address, device_map, loop.create_future,
                    DeviceReaderConfig(timeout=15, use_encryption=self.encrypted),
                    lock=asyncio.Lock(), ble_client=client)
                data = await reader.read(only_registers=[ReadableRegisters(*block) for block in self.plan])
        if not data:
            raise RuntimeError("Немає відповіді. Перевір Bluetooth, відстань і з’єднання на телефоні.")
        data = normalize(data, self.profile.aliases)
        self.last_read = time.monotonic()
        self.reading.emit(data)
        self.status.emit("Підключено · оновлення кожні 15 с")
        return data

    async def write(self, field, value):
        if not self.profile.controls:
            raise RuntimeError('Ця модель поки підтримує тільки читання')
        if self.paused:
            raise RuntimeError("Bluetooth звільнено для телефону")
        if self.encrypted:
            raise RuntimeError("Ця версія підтримує лише читання зашифрованих станцій.")
        if field not in WRITABLE:
            raise ValueError("Непідтримувана команда")
        if field in {"ctrl_ac", "ctrl_dc"} and type(value) is not bool:
            raise ValueError("Некоректне значення перемикача")
        if field == "ctrl_charging_mode" and value not in {"SILENT", "STANDARD", "TURBO"}:
            raise ValueError("Некоректний режим заряджання")
        if not self.last_read or time.monotonic() - self.last_read > 6:
            raise RuntimeError("Спочатку онови дані станції")
        command = self.device.build_write_command(field, value)
        if command is None:
            raise RuntimeError("Команда недоступна для цієї моделі")
        live = await self.ensure_live()
        # Read back actual state. A successful GATT write alone is not confirmation.
        await live.client.write_gatt_char(WRITE_UUID, bytes(command), response=live.write_with_response)
        await asyncio.sleep(.25)
        data = await self.read()
        if data.get(field) != value:
            raise RuntimeError("Станція не підтвердила зміну. Перевір стан у застосунку BLUETTI.")

    async def work(self):
        self.loop = asyncio.get_running_loop()
        self.task = asyncio.current_task()
        next_poll = float("inf")
        failures = 0
        heartbeat = time.monotonic()
        try:
            await self.work_loop(next_poll, failures, heartbeat)
        except asyncio.CancelledError:
            pass
        finally:
            await self.disconnect()
            self.task = None
            self.loop = None

    @staticmethod
    def failure_message(exc):
        if isinstance(exc, TimeoutError):
            return "Станція не відповіла. Перевір відстань і з’єднання на телефоні."
        if isinstance(exc, BleakError):
            if "scanner" in str(exc).lower() or "bluetooth turned on" in str(exc).lower():
                return "Увімкни Bluetooth у Windows або перевір адаптер."
            return "Помилка Bluetooth. Перевір адаптер, відстань і з’єднання на телефоні."
        return str(exc) or "Не вдалося отримати дані станції."

    async def work_loop(self, next_poll, failures, heartbeat):
        while not self.isInterruptionRequested():
            now = time.monotonic()
            if now - heartbeat > 8 and self.live:
                await self.disconnect()
                self.status.emit("Відновлюю з’єднання після паузи…")
            heartbeat = now
            try:
                action, payload = self.commands.get_nowait()
            except queue.Empty:
                if self.address and not self.paused and time.monotonic() >= next_poll:
                    action, payload = "read", None
                else:
                    await asyncio.sleep(.15)
                    continue
            try:
                cycle_start = time.monotonic()
                if action == "pause":
                    self.paused = True
                    self.last_read = 0
                    if not await self.disconnect():
                        raise RuntimeError("Не вдалося звільнити Bluetooth. Повтори спробу.")
                    self.paused_changed.emit(True)
                    self.status.emit("Bluetooth звільнено · можна підключити телефон")
                elif action == "resume":
                    self.paused = False
                    self.paused_changed.emit(False)
                    if self.address:
                        self.status.emit("Підключаюся…")
                        await self.read()
                elif action == "scan":
                    await self.scan()
                elif action == "select":
                    await self.disconnect()
                    self.paused = False
                    self.paused_changed.emit(False)
                    if self.address.casefold() != payload["address"].casefold():
                        self.prefer_uncached = False
                    self.address = payload["address"]
                    self.profile = get_profile(payload.get('model','AC180P'))
                    self.device = self.profile.device_factory()
                    self.plan = self.profile.read_plan(self.device)
                    self.encrypted = payload.get("encrypted", False)
                    self.last_read = 0
                    self.selected.emit(payload)
                    self.status.emit("Підключаюся…")
                    await self.read()
                elif action == "read" and self.address and not self.paused:
                    await self.read()
                elif action == "write" and self.address and not self.paused:
                    self.status.emit("Змінюю налаштування…")
                    await self.write(*payload)
                    self.command_done.emit(True, "Станція підтвердила зміну")
                failures = 0
            except Exception as exc:
                if action != "scan":
                    self.last_read = 0
                    await self.disconnect()
                # Exception text from WinRT can contain a device identifier.
                logging.warning("Bluetooth operation %s failed (%s)", action, type(exc).__name__)
                message = self.failure_message(exc)
                if action == "scan":
                    self.scan_failed.emit(message)
                else:
                    failures += 1
                    self.failure.emit(message)
                    if self.address and not self.paused and action in {"read", "select", "resume"}:
                        delay = min(15, 2 ** min(failures, 4))
                        self.retrying.emit(f"Повтор через {delay} с · {message}")
                    if action == "write":
                        self.command_done.emit(False, message)
            finally:
                interval = 15 if self.encrypted else 1
                next_poll = max(time.monotonic() + .1, cycle_start + interval)
                if failures:
                    next_poll = time.monotonic() + min(15, 2 ** min(failures, 4))
                heartbeat = time.monotonic()
