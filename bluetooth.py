from __future__ import annotations
import uuid
import bleak
import collections
import collections.abc
import asyncio
import bleak.backends.characteristic
import bleak.backends.bluezdbus.utils
import bleak.backends.service


def expand_uuid(uuid: str | int):
    return f'{uuid:0>8}-0000-1000-8000-00805f9b34fb'


class Cache:
    """
    BLE supports no more than 7 concurrent devices,
    and disconnect/connect incurs 1 second delay each.
    This is an LRU cache.
    """

    def __init__(self, capacity: int = 6):
        self.capacity = capacity
        self.queue: collections.OrderedDict[Client, None] = collections.OrderedDict()
        self.lock = asyncio.Lock()


cache = Cache()


class Client(bleak.BleakClient):
    '''
    A wrapper of bleak.BleakClient
    '''

    def __init__(self, address: str, cache: Cache = cache):

        def disconnected_callback(_):
            print(f'<5>bluetooth.Client.disconnected_callback {self.address}')
            self.cache.queue.pop(self, None)

        super().__init__(address, disconnected_callback=disconnected_callback)
        self.cache = cache
        self.connect_finalizer = None

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
        async with self.cache.lock:
            if not self.connect_finalizer:
                self.connect_finalizer = self.connect_finalizer_body()
                await self.connect_finalizer.__anext__()
            self.cache.queue[self] = None
            self.cache.queue.move_to_end(self, last=True)
            while len(self.cache.queue) > self.cache.capacity:
                await self.cache.queue.popitem(last=False)[0].disconnect()
            if not self.is_connected:
                for _ in range(10):
                    try:
                        return await super().connect()
                    except bleak.exc.BleakDBusError as error:
                        if error.dbus_error == 'org.bluez.Error.Failed' and error.dbus_error_details == 'le-connection-abort-by-local':
                            print(f'<4>bluetooth.Client.connect {self.address} retry because dbus: {error.dbus_error_details}')
                            self.cache.lock.release()
                            await asyncio.sleep(3)
                            await self.cache.lock.acquire()
                        else:
                            raise
                    except bleak.exc.BleakDeviceNotFoundError as error:
                        await bleak.BleakScanner.find_device_by_address(error.identifier)
                        self.cache.lock.release()
                        await asyncio.sleep(3)
                        await self.cache.lock.acquire()

    async def send(self,
                   char_specifier: bleak.backends.characteristic.BleakGATTCharacteristic | int | str | uuid.UUID,
                   data: collections.abc.Iterable[int],
                   response: bool = False,
                   retry: int = 10):
        '''
        send application data to the specified GATT characteristic.
        connection limit and retry will be handled automatically.

        data: an iterable yielding integers in range(256).
        '''
        for _ in range(retry):
            try:
                await self.connect()
                return await super().write_gatt_char(char_specifier=char_specifier, data=data, response=response)
            except bleak.BleakError as error:
                print(f'<4>bluetooth.Client.send {self.address} retry because: {error}')
                await self.disconnect()

    async def recv(self, char_specifier: bleak.backends.characteristic.BleakGATTCharacteristic | int | str | uuid.UUID):
        future: asyncio.Future[tuple[int, bytearray]] = asyncio.Future()
        future.add_done_callback(lambda _: super().stop_notify(char_specifier))
        await self.connect()
        await super().start_notify(char_specifier, lambda sender, data: future.set_result((sender, data)))
        return await future

    async def start_notify_stream(self, char_specifier: bleak.backends.characteristic.BleakGATTCharacteristic | int | str | uuid.UUID, **kwargs):
        loop = asyncio.get_event_loop()
        queue = asyncio.Queue()
        asyncio.create_task(super().start_notify(char_specifier, lambda sender, data: loop.call_soon_threadsafe(queue.put_nowait, (sender, data)),
                                                 **kwargs))
        while True:
            yield await queue.get()
