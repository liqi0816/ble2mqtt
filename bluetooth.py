import bleak
import collections
import asyncio


class Cache:
    """
    BLE supports no more than 7/8 concurrent devices,
    and disconnect/connect incurs 1 second delay each.
    This is an LRU cache.
    """

    def __init__(self, capacity: int = 6):
        self.capacity = capacity
        self.queue = collections.OrderedDict()
        self.connecting_lock = asyncio.Lock()


cache = Cache()


def expand_uuid(uuid):
    return f'{uuid:0>8}-0000-1000-8000-00805f9b34fb'


def gen_checksum(data):
    if isinstance(data, str):
        print(data)
    checksum = 0
    for byte in data:
        checksum ^= byte
    return checksum


class Client(bleak.BleakClient):
    def __init__(self, address: str, cache: Cache = cache):
        super().__init__(address)
        self.cache = cache
        self.set_disconnected_callback(lambda _: self.cache.queue.pop(self, None))
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
        except GeneratorExit:
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
                await self.cache.queue.popitem(last=False).disconnect()
            for _ in range(10):
                try:
                    return await super().connect()
                except bleak.BleakError as retry:
                    if retry.args == ('org.bluez.Error.Failed: Software caused connection abort',):
                        self.cache.connecting_lock.release()
                        await asyncio.sleep(3)
                        await self.cache.connecting_lock.acquire()
                    else:
                        raise

    async def disconnect(self):
        self.cache.queue.pop(self, None)
        return await super().disconnect()

    async def send(self, char_specifier, data_array, response=False, retry=10):
        data = bytearray((*data_array, gen_checksum(data_array)))
        for _ in range(retry):
            try:
                if not self.is_connected:
                    await self.connect()
                return await super().write_gatt_char(char_specifier=char_specifier, data=data, response=response)
            except bleak.exc.BleakError:
                await self.disconnect()

    async def recv(self, char_specifier):
        future = asyncio.Future()
        future.add_done_callback(super().stop_notify, char_specifier)
        await super().start_notify(char_specifier, lambda sender, data: future.set_result((sender, data)))
        return future

    async def __aenter__(self):
        assert await self.connect()

    async def __aexit__(self, exc_type, exc_value, traceback):
        assert await self.disconnect()
