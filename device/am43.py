import asyncio
import bluetooth
import datetime


class AM43():
    charac_id = {
        'state': bluetooth.expand_uuid('fe51'),
    }
    state_id = {
        'move': 0x0d,
        'stop': 0x0a,
        'battery': 0xa2,
        'light': 0xaa,
        'position': 0xa7,
    }
    message_magic = 0x9a

    def __init__(self, address, semaphore=bluetooth.semaphore):
        self.client = bluetooth.Client(address, semaphore)
        self.state = {
            'battery': None,
            'light': None,
            'position': None,
        }
        self.state_time = {state_name: datetime.datetime.now() for state_name in self.state}

    async def init(self):
        await self.client.connect()
        await self.client.start_notify(AM43.charac_id['state'], self.on_notify)
        await self.query()

    def on_notify(self, sender: int, data: bytearray):
        try:
            state_name = next(state_name for state_name, state_id in AM43.state_id.items() if state_id == data[1])

            if state_name == 'battery':
                self.state['battery'] = data[7]
            elif state_name == 'position':
                self.state['position'] = data[5]
            elif state_name == 'light':
                self.state['light'] = data[4] * 12.5
            print(f'{self.statwe[state_name]=}')
            self.state_time[state_name] = datetime.datetime.now()
        except StopIteration:
            pass

    async def query(self):
        for state_name in self.state:
            await self.client.send(AM43.charac_id['state'], [
                AM43.message_magic, AM43.state_id[state_name],
                (_len := 1), (_body := 0x01),
            ])

    async def xx(self, position, interval=0.5, battery=95):
        while self.state['battery'] > battery:
            await asyncio.sleep(interval)
            self.client.send(AM43.charac_id['state'], [
                AM43.message_magic, AM43.state_id['position'],
                (_len := 1), (_body := 0x01),
            ]))
        while self.state['battery'] > battery:
            await asyncio.sleep(interval)
            asyncio.create_task(self.client.send(AM43.charac_id['state'], [
                AM43.message_magic, AM43.state_id['battery'],
                (_len := 1), (_body := 0x01),
            ]))

    async def move(self, position):
        return await self.client.send(AM43.charac_id['state'], [
            AM43.message_magic, AM43.state_id['move'],
            (_len := 1), position,
        ])

    async def open(self):
        return await self.move(0)

    async def close(self):
        return await self.move(100)

    async def stop(self):
        return await self.client.send(AM43.charac_id['state'], [
            AM43.message_magic, AM43.state_id['stop'],
            (_len := 1), (_body := 0xcc),
        ])

    async def bindMQTT(self, mqtt):
        pass
