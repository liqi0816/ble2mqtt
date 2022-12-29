from __future__ import annotations

import asyncio
import collections
import collections.abc
import uuid

import bleak
import bleak.backends.bluezdbus.utils
import bleak.backends.characteristic
import bleak.backends.device
import bleak.backends.service
import pyee


def expand_uuid(uuid: str | int):
    return f'{uuid:0>8}-0000-1000-8000-00805f9b34fb'


class Concurrency:
    """
    BLE supports no more than 7 concurrent devices,
    and connect/disconnect incurs 1 second delay each.
    This is an FIFO concurrency control
    """

    def __init__(self, capacity: int = 6):
        self.capacity = capacity
        self.queue: collections.OrderedDict[Client, None] = collections.OrderedDict()
        self.lock = asyncio.Lock()


concurrency = Concurrency()


class EventEmitter(pyee.EventEmitter):

    def once_async(self, event):
        future = asyncio.Future()
        self.once(event, lambda *data: future.set_result(data))
        return future

    async def on_async(self, event):
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        listener = lambda *data: loop.call_soon_threadsafe(queue.put_nowait, data)
        try:
            self.add_listener(event, listener)
            while True:
                yield await queue.get()
        finally:
            self.remove_listener(event, listener)


class Client(bleak.BleakClient):
    '''
    A wrapper of bleak.BleakClient
    
    methods here should
    1. hide connect-disconnect from consumer
    2. work across connect-disconnect-reconnect
    3. observe concurrency limit
    4. retry automatically if needed
    '''

    def __init__(self, address: bleak.backends.device.BLEDevice | str, concurrency: Concurrency = concurrency):
        event = EventEmitter()
        super().__init__(address, disconnected_callback=lambda _: self.event.emit('disconnect'))
        self.event = event
        self.concurrency = concurrency
        self.connect_finalizer = None
        self.event.on('disconnect', lambda: self.concurrency.queue.pop(self, None))
        self.event.on('disconnect', lambda: print(f'<5>bluetooth.Client.event.disconnect {self.address}'))
        self.event.on('connect', lambda: print(f'<6>bluetooth.Client.event.connect {self.address}'))

    async def connect_finalizer_body(self):
        """
        This is the fallback finalizer.

        async generator finalizer hack: 
        we need a async version weakref.finalize
        but such thing does not exist yet.
        asyncgen however can register a reliable finalizer implicitly.
        see https://www.python.org/dev/peps/pep-0525/#finalization
        """
        try:
            yield
        finally:
            await self.disconnect()

    # first queue, then backend
    async def connect(self):
        async with self.concurrency.lock:
            if not self.connect_finalizer:
                self.connect_finalizer = self.connect_finalizer_body()
                await self.connect_finalizer.__anext__()
            self.concurrency.queue[self] = None
            self.concurrency.queue.move_to_end(self, last=True)
            while len(self.concurrency.queue) > self.concurrency.capacity:
                await self.concurrency.queue.popitem(last=False)[0].disconnect()
            if not self.is_connected:
                for _ in range(10):
                    try:
                        data = await super().connect()
                        self.event.emit('connect')
                        return data
                    except bleak.exc.BleakDBusError as error:
                        if error.dbus_error == 'org.bluez.Error.Failed' and error.dbus_error_details == 'le-connection-abort-by-local':
                            print(f'<4>bluetooth.Client.connect {self.address} retry because dbus: {error.dbus_error_details}')
                            self.concurrency.lock.release()
                            await asyncio.sleep(3)
                            await self.concurrency.lock.acquire()
                        else:
                            raise
                    except bleak.exc.BleakDeviceNotFoundError as error:
                        await bleak.BleakScanner.find_device_by_address(error.identifier)
                        self.concurrency.lock.release()
                        await asyncio.sleep(3)
                        await self.concurrency.lock.acquire()

    async def send(self,
                   char_specifier: bleak.backends.characteristic.BleakGATTCharacteristic | int | str | uuid.UUID,
                   data: collections.abc.Iterable[int],
                   response: bool = False,
                   retry: int = 10):
        for _ in range(retry):
            try:
                await self.connect()
                return await self.write_gatt_char(char_specifier=char_specifier, data=data, response=response)
            except bleak.BleakError as error:
                print(f'<4>bluetooth.Client.send {self.address} retry because: {error}')
                await self.disconnect()
                await asyncio.sleep(3)

    async def recv(self, char_specifier: bleak.backends.characteristic.BleakGATTCharacteristic | int | str | uuid.UUID):
        future: asyncio.Future[tuple[int, bytearray]] = asyncio.Future()
        await self.connect()
        await self.start_notify(char_specifier, lambda sender, data: future.set_result((sender, data)))
        try:
            return await future
        finally:
            await self.stop_notify(char_specifier)

    async def recv_stream(self, char_specifier: bleak.backends.characteristic.BleakGATTCharacteristic | int | str | uuid.UUID, **kwargs):
        loop = asyncio.get_running_loop()
        future = asyncio.Future()
        queue = asyncio.Queue()
        await self.connect()
        await self.start_notify(char_specifier, lambda sender, data: loop.call_soon_threadsafe(queue.put_nowait, (sender, data)), **kwargs)
        self.event.on('disconnect', lambda: future.set_exception(StopAsyncIteration()))
        try:
            while True:
                yield await asyncio.wait((queue.get(), future), asyncio.FIRST_EXCEPTION)
        finally:
            await self.stop_notify(char_specifier)

    async def recv_stream_opportunistic(self, char_specifier: bleak.backends.characteristic.BleakGATTCharacteristic | int | str | uuid.UUID,
                                        **kwargs):
        ''' This method passively listen for messages as they come by. It does not call `connect` implicitly. '''
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        listener = lambda sender, data: loop.call_soon_threadsafe(queue.put_nowait, (sender, data))
        if self.is_connected:
            await self.start_notify(char_specifier, listener, **kwargs)
        self.event.on('connect', lambda: asyncio.create_task(self.start_notify(char_specifier, listener, **kwargs)))
        try:
            while True:
                yield await queue.get()
        finally:
            await self.stop_notify(char_specifier)
