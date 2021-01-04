import weakref
import bleak
import collections
import async_tail


class Cache():
    def __init__(self, capacity=6):
        self.capacity = capacity
        self.queue = collections.OrderedDict()


cache = Cache()


def expand_uuid(uuid):
    return f'{uuid:0>8}-0000-1000-8000-00805f9b34fb'


def gen_checksum(data):
    checksum = 0
    for byte in data:
        checksum ^= byte
    return checksum


class Client(bleak.BleakClient):
    def __init__(self, address, cache=cache):
        super().__init__(address)
        self.cache = cache
        self.set_disconnected_callback(self.__del__)
        weakref.finalize(self, self.__del__)

    # first queue, then backend
    async def connect(self):
        self.cache.queue[self] = None
        self.cache.queue.move_to_end(self, last=True)
        while len(self.cache.queue) > self.cache.capacity:
            await self.cache.queue.popitem(last=False).disconnect()
        return await super().connect()

    async def disconnect(self):
        self.cache.queue.pop(self, None)
        return await super().disconnect()

    async def send(self,
                   char_specifier, data_array, response=False,
                   retry=10):
        data = bytearray((*data_array, gen_checksum(data_array)))
        for i in range(retry):
            try:
                await self.connect()
                return await super().write_gatt_char(char_specifier=char_specifier, data=data, response=response)
            except bleak.exc.BleakError:
                await self.disconnect()

    async def __aenter__(self):
        await self.connect()
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.disconnect()

    def __del__(self, _=None):
        return async_tail.run_back_coro(self.disconnect())
