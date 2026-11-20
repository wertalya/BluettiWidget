"""BLUETTI AC180P BLE worker. All Bluetooth operations stay off the UI thread."""
import asyncio
import logging
import queue
import time

from PySide6.QtCore import QThread, Signal
from bleak import BleakClient, BleakScanner
from bluetti_bt_lib import DeviceReader, DeviceReaderConfig
from bluetti_bt_lib.devices.ac180p import AC180P
from bluetti_bt_lib.const import WRITE_UUID, NOTIFY_UUID
from bluetti_bt_lib.registers import ReadableRegisters
from models import detect_profile, get_profile

WRITABLE = {"ctrl_ac", "ctrl_dc", "ctrl_charging_mode"}


class LiveSession:
    """One BLE connection, sequential requests and fragmented reply assembly."""
    def __init__(self, client):
        self.client = client
        self.pending = None
        self.buffer = bytearray()
        self.register = None
        self.write_with_response = True

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
            self.pending.set_exception(ValueError("Пошкоджена відповідь Bluetooth"))
        elif self.register.is_exception_response(frame):
            self.pending.set_exception(ValueError("Станція відхилила запит даних"))
        elif frame[0:2] != b'\x01\x03' or len(frame) != self.register.response_size():
            self.pending.set_exception(ValueError("Неочікувана відповідь станції"))
        else:
            self.pending.set_result(frame)

    async def read(self, device):
        data = {}
        for address, count in [(102, 1), (140, 8), (2011, 2), (2020, 1)]:
            self.register = ReadableRegisters(address, count)
            self.buffer.clear()
            self.pending = asyncio.get_running_loop().create_future()
            try:
                await self.client.write_gatt_char(WRITE_UUID, bytes(self.register), response=self.write_with_response)
                frame = await asyncio.wait_for(self.pending, timeout=3)
                data.update(device.parse(address, self.register.parse_response(frame)))
            finally:
                self.pending = None
        return data


def normalize(data):
    result = {}
    for key, value in data.items():
        key = getattr(key, "value", key)
        result[key] = getattr(value, "name", value)
    soc = result.get("total_battery_percent")
    if type(soc) is not int or not 0 <= soc <= 100:
        raise ValueError("Станція не повернула коректний рівень заряду")
    return result


class BluetoothWorker(QThread):
    devices = Signal(list)
    reading = Signal(dict)
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
        self.device = AC180P()
        self.profile = get_profile('AC180P')
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
                logging.warning("Bluetooth disconnect failed", exc_info=True)
                return False
        return True

    async def ensure_live(self):
        if self.live and self.live.client.is_connected:
            return self.live
        await self.disconnect()
        # Wait for a complete advertising/scan-response cycle on Windows. The
        # first packet can precede a usable connection (notably after release).
        self.status.emit("Шукаю станцію · до 8 секунд…")
        found = await BleakScanner.discover(timeout=8, return_adv=True)
        device = next((item for item, advertisement in found.values()
                       if item.address.lower() == self.address.lower()), None)
        if device is None:
            raise RuntimeError("Станція недоступна. Перевір відстань і з’єднання на телефоні.")
        self.status.emit("Станцію знайдено · підключаюся…")
        # Let Windows use its normal GATT cache policy, matching the proven
        # diagnostic path. Forcing uncached discovery can hang after reconnect.
        client = BleakClient(device, timeout=20)
        self.live = LiveSession(client)
        await client.connect()
        characteristic = client.services.get_characteristic(WRITE_UUID)
        if characteristic is None:
            raise RuntimeError("У станції немає очікуваного Bluetooth-сервісу")
        self.live.write_with_response = 'write' in characteristic.properties
        self.status.emit("Отримую живі показники…")
        await client.start_notify(NOTIFY_UUID, self.live.notification)
        return self.live

    def submit(self, action, payload=None):
        self.commands.put((action, payload))

    def run(self):
        asyncio.run(self.work())

    async def scan(self):
        self.status.emit("Шукаю AC180P поблизу…")
        found = await BleakScanner.discover(timeout=8, return_adv=True)
        devices = []
        for dev, adv in found.values():
            name = adv.local_name or dev.name or ""
            profile = detect_profile(name)
            if profile is None:
                continue
            marker = b"".join(adv.manufacturer_data.values())
            devices.append({"name": name, "model":profile.model, "address": dev.address,
                            "encrypted": b"BLUETTE" in marker})
        self.devices.emit(devices)
        self.status.emit(f"Знайдено станцій: {len(devices)}" if devices else
                         "Станцію не знайдено. Увімкни її та закрий BLUETTI на телефоні.")

    async def read(self):
        loop = asyncio.get_running_loop()
        if not self.encrypted:
            async with asyncio.timeout(40):
                live = await self.ensure_live()
                data = await live.read(self.device)
            data = normalize(data)
            self.last_read = time.monotonic()
            self.reading.emit(data)
            self.status.emit("Живі дані · до 2 оновлень на секунду")
            return data
        # Use the discovered device object directly. Avoid a second short scan
        # in the library, which can miss intermittent Windows advertisements.
        async with asyncio.timeout(30):
            device = await BleakScanner.find_device_by_address(self.address, timeout=10)
            if device is None:
                raise RuntimeError("Станція недоступна. Перевір відстань і з’єднання на телефоні.")
            async with BleakClient(device, timeout=12) as client:
                reader = DeviceReader(self.address, self.device, loop.create_future,
                    DeviceReaderConfig(timeout=15, use_encryption=self.encrypted),
                    lock=asyncio.Lock(), ble_client=client)
                data = await reader.read()
        if not data:
            raise RuntimeError("Немає відповіді. Перевір Bluetooth, відстань і з’єднання на телефоні.")
        data = normalize(data)
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
            raise RuntimeError("Команда недоступна для AC180P")
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
                    await self.disconnect()
                    await self.scan()
                elif action == "select":
                    await self.disconnect()
                    self.paused = False
                    self.paused_changed.emit(False)
                    self.address = payload["address"]
                    self.profile = get_profile(payload.get('model','AC180P'))
                    self.device = self.profile.device_factory()
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
                await self.disconnect()
                logging.exception("Bluetooth operation %s failed", action)
                failures += 1
                message = str(exc) or "Час очікування минув. Перевір Bluetooth і з’єднання станції."
                self.failure.emit(message)
                if action == "write":
                    self.command_done.emit(False, message)
            finally:
                interval = 15 if self.encrypted else .5
                if failures:
                    interval = min(15, 2 ** min(failures, 4))
                next_poll = max(time.monotonic() + .1, cycle_start + interval)
                heartbeat = time.monotonic()
