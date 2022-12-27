from __future__ import annotations
import uuid
import bleak
import collections
import collections.abc
import asyncio
import bleak.backends.characteristic
import bleak.backends.bluezdbus.utils
import bleak.backends.service


class Cache:
    """
    BLE supports no more than 7/8 concurrent devices,
    and disconnect/connect incurs 1 second delay each.
    This is an LRU cache.
    """

    def __init__(self, capacity: int = 6):
        self.capacity = capacity
        self.queue: collections.OrderedDict[Client, None] = collections.OrderedDict()
        self.connecting_lock = asyncio.Lock()


cache = Cache()


def expand_uuid(uuid: str | int):
    return f'{uuid:0>8}-0000-1000-8000-00805f9b34fb'


class Client(bleak.BleakClient):
    '''
    A wrapper of bleak.BleakClient
    '''

    def __init__(self, address: str, cache: Cache = cache):
        super().__init__(address, disconnected_callback=lambda _: self.cache.queue.pop(self, None))
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
        async with self.cache.connecting_lock:
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
                    except bleak.backends.bluezdbus.utils.BleakDBusError as dbus_error:
                        if dbus_error.dbus_error == 'org.bluez.Error.Failed' and dbus_error.dbus_error_details == 'Software caused connection abort':
                            print(f'<4>bluetooth.Client.connect retry dbus because: {dbus_error.dbus_error_details}')
                            self.cache.connecting_lock.release()
                            await asyncio.sleep(3)
                            await self.cache.connecting_lock.acquire()
                        else:
                            raise

    async def disconnect(self):
        self.cache.queue.pop(self, None)
        print(f'<5>bluetooth.Client disconnecting {self.address}')
        return await super().disconnect()

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
                print(f'<4>bluetooth.Client.send retry because:\n{error}')
                await self.disconnect()

    async def recv(self, char_specifier: bleak.backends.characteristic.BleakGATTCharacteristic | int | str | uuid.UUID):

        def stop_notify(_):
            super().stop_notify(char_specifier)

        future: asyncio.Future[tuple[int, bytearray]] = asyncio.Future()
        future.add_done_callback(stop_notify)
        await self.connect()
        await super().start_notify(char_specifier, lambda sender, data: future.set_result((sender, data)))
        return await future

    async def __aenter__(self):
        assert await self.connect()

    async def __aexit__(self, exc_type, exc_value, traceback):
        assert await self.disconnect()
