import asyncio
import bluetooth
import datetime
import json
import pyee


class AM43(pyee.EventEmitter):
    charac_id = {
        'state': bluetooth.expand_uuid('fe51'),
    }
    state_id = {
        'move': 0x0d,
        'stop': 0x0a,
        'battery': 0xa2,
        'illuminance': 0xaa,
        'position': 0xa7,
    }
    message_magic = 0x9a

    def __init__(self, address, cache=None, identifier='', *, reverse=False):
        super().__init__()
        self.client = bluetooth.Client(address, cache)
        self.identifier = identifier or f'am43_{address.replace(":", "").lower()}'
        self.state = {
            'battery': None,
            'illuminance': None,
            'position': None,
        }
        # self.state_time = {state_name: datetime.datetime.now() for state_name in self.state}

    async def init(self):
        await self.client.connect()
        await self.client.start_notify(AM43.charac_id['state'], self.on_notify)
        await self.query()
        self.emit('init')
        return self

    async def finalize(self):
        await self.client.disconnect()
        self.emit('finalize')
        return self

    def on_notify(self, sender: int, data: bytearray):
        try:
            state_name = next(state_name
                              for state_name, state_id in AM43.state_id.items()
                              if state_id == data[1] and state_name in self.state)
            if state_name == 'battery':
                self.state['battery'] = data[7]
            elif state_name == 'position':
                self.state['position'] = data[5]
            elif state_name == 'illuminance':
                self.state['illuminance'] = data[4] * 12.5
            # self.state_time[state_name] = datetime.datetime.now()
            self.emit('statechange', self.state)
        except (StopIteration, IndexError):
            pass

    async def query(self):
        for state_name in self.state:
            onstatechange = asyncio.Future()
            self.once('statechange', onstatechange.set_result)
            await asyncio.gather(
                onstatechange,
                self.client.send(AM43.charac_id['state'], [
                    AM43.message_magic, AM43.state_id[state_name],
                    (_len := 1), (_body := 0x01),
                ]),
            )

    async def sync_position(self, position, interval=0.7, battery=90, timeout=30, tolerance=1):
        for _ in range(int(timeout / interval)):
            if abs(self.state['position']-position) <= tolerance:
                return 'success'
            if (self.state['battery'] or 0) < battery:
                return 'battery'
            await asyncio.gather(
                asyncio.sleep(interval),
                self.client.send(AM43.charac_id['state'], [
                    AM43.message_magic, AM43.state_id['position'],
                    (_len := 1), (_body := 0x01),
                ]),
            )
        else:
            return 'timeout'

    async def move(self, position: int, timeout=60):
        return (
            asyncio.create_task(self.sync_position(position)),
            await self.client.send(AM43.charac_id['state'], [
                AM43.message_magic, AM43.state_id['move'],
                (_len := 1), position,
            ]),
        )

    async def open(self):
        return await self.move(0)

    async def close(self):
        return await self.move(100)

    async def stop(self):
        return (
            asyncio.create_task(self.query()),
            await self.client.send(AM43.charac_id['state'], [
                AM43.message_magic, AM43.state_id['stop'],
                (_len := 1), (_body := 0xcc),
            ]),
        )

    async def bindMQTT(self, mqtt, device_topic, homeassistant_discovery_topic='homeassistant'):
        self.on('statechange', lambda state: asyncio.create_task(
            mqtt.publish(device_topic, json.dumps(state).encode('utf8'))
        ))
        device = {
            'connections': [['bluetooth', self.client.address]],
            'identifiers': self.identifier,
            'manufacturer': 'Generic',
            'model': 'AM43 Blind Drive Motor',
            'name': self.identifier,
        }
        await mqtt.publish(f'{homeassistant_discovery_topic}/cover/{self.identifier}/config', json.dumps({
            'availability': {
                'payload_available': 'online',
                'payload_not_available': 'offline',
                'topic': f'{device_topic}/availability',
            },
            'command_topic': f'{device_topic}/set/state',
            'device': device,
            'name': device["name"],
            'payload_close': 'CLOSE',
            'payload_open': 'OPEN',
            'payload_stop': 'STOP',
            'position_closed': 100,
            'position_open': 0,
            'position_topic': device_topic,
            'set_position_topic': f'{device_topic}/set/position',
            'unique_id': self.identifier,
            'value_template': '{{value_json["position"]}}',
        }).encode('utf8'))
        await mqtt.publish(f'{homeassistant_discovery_topic}/sensor/{self.identifier}_battery/config', json.dumps({
            'availability': {
                'payload_available': 'online',
                'payload_not_available': 'offline',
                'topic': f'{device_topic}/availability',
            },
            'device': device,
            'device_class': 'battery',
            'name': f'{device["name"]} battery',
            'state_topic': device_topic,
            'unique_id': f'{self.identifier}_battery',
            'unit_of_measurement': '%',
            'value_template': '{{value_json["battery"]}}',
        }).encode('utf8'))
        await mqtt.publish(f'{homeassistant_discovery_topic}/sensor/{self.identifier}_illuminance/config', json.dumps({
            'availability': {
                'payload_available': 'online',
                'payload_not_available': 'offline',
                'topic': f'{device_topic}/availability',
            },
            'device': device,
            'device_class': 'illuminance',
            'name': f'{device["name"]} illuminance',
            'state_topic': device_topic,
            'unique_id': f'{self.identifier}_illuminance',
            'unit_of_measurement': '%',
            'value_template': '{{value_json["illuminance"]}}',
        }).encode('utf8'))
        await mqtt.publish(f'{device_topic}/availability', 'online'.encode('utf8'), retain=False)
        await mqtt.publish(device_topic, json.dumps(self.state).encode('utf8'))

    async def handleMQTT(self, topic, data):
        if len(topic) > 0:
            if topic[0] == 'set':
                if len(topic) > 1:
                    items = {topic[1]: data}
                else:
                    items = json.loads(data)
                for state_name, data in items.items():
                    if state_name == 'state':
                        if data == 'OPEN':
                            return await self.open()
                        elif data == 'STOP':
                            return await self.stop()
                        elif data == 'CLOSE':
                            return await self.close()
                    elif state_name == 'position':
                        return await self.move(int(data))
            elif topic[0] == 'get':
                if len(topic) > 1:
                    items = {topic[1]: data}
                else:
                    items = json.loads(data)
                pass

    def __aenter__(self):
        return self.open()

    def __aexit__(self, exc_type, exc_value, traceback):
        return self.close()


Device = AM43
