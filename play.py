# bluetoothctl disconnect '02:94:A3:5F:1D:1D'
import asyncio

class Foo():
    def __init__(self, i=0):
        self.i = i
        self.bar = self.xx().__anext__

    async def xx(self):
        try:
            while True:
                await asyncio.sleep(1)
                yield self.i
        finally:
            await asyncio.sleep(1)
            print('gracefully exit\n', end='')


async def main():
    a = Foo()
    print(f'{await a.bar()=}')
    del a


asyncio.run(main())
