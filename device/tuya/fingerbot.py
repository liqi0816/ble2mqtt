from __future__ import annotations
import asyncio
import bluetooth
import json
import pyee
from . import util
import itertools


class TuyaFingerBot(pyee.EventEmitter):
    CHAR_ID = {
        'notification': bluetooth.expand_uuid('2b10'),
        'state': bluetooth.expand_uuid('2b11'),
    }
    ACTION = {
        'ARM_DOWN_PERCENT': 9,
        'ARM_UP_PERCENT': 15,
        'CLICK_SUSTAIN_TIME': 10,
        'TAP_ENABLE': 17,
        'MODE': 8,
        'INVERT_SWITCH': 11,
        'TOGGLE_SWITCH': 2,
        'CLICK': 101,
        'PROG': 121,
    }

    def __init__(self, client: bluetooth.Client, device_id: str, uuid: str, local_key: str, identifier=''):
        super().__init__()
        self.client = client
        self.identifier = identifier or f'tuya_fingerbot_{client.address.replace(":", "").lower()}'
        self.device_id = device_id.encode('ascii')
        self.uuid = uuid.encode('ascii')
        self.session = util.TuyaSession(local_key)
        self.sn_counter = itertools.count(1)

    async def init(self):
        await self.client.connect()
        stream = util.Readable()
        asyncio.create_task(self.parse_stream(stream))
        await self.client.start_notify(TuyaFingerBot.CHAR_ID['notification'], lambda sender, data: stream.push(data))
        self.emit('init')
        await self.send_request(util.create_device_info_request(next(self.sn_counter), self.session))
        return self
        
    async def finalize(self):
        await self.client.disconnect()
        self.emit('finalize')
        return self

    async def parse_stream(self, stream: util.Readable):
        async for message_raw in util.merge_packets(stream):
            message = util.parse_message(message_raw, self.session)
            if message.get('update_session', False):
                await self.send_request(util.create_pair_request(next(self.sn_counter), self.session, uuid=self.uuid, device_id=self.device_id))
                self.emit('pairing')
            elif message['code'] == util.TuyaCode.FUN_SENDER_PAIR:
                self.emit('paired')

    async def send_request(self, request: bytes):
        for packet in util.split_packets(request):
            await self.client.send(TuyaFingerBot.CHAR_ID['state'], packet)

    async def press(self):
        await self.send_request(util.create_command_request(next(self.sn_counter), self.session, (
            (self.ACTION['MODE'], bytes((util.TuyaDataType.ENUM, 1, 0))),
            (self.ACTION['ARM_DOWN_PERCENT'], 80),
            (self.ACTION['ARM_UP_PERCENT'], 0),
            (self.ACTION['CLICK_SUSTAIN_TIME'], 0),
            (self.ACTION['CLICK'], True),
        )))

    async def bindMQTT(self, mqtt, device_topic: str, homeassistant_discovery_topic: str = None) -> None:
        self.on('finalize', lambda state: asyncio.create_task(mqtt.publish(f'{device_topic}/availability', 'offline'.encode('utf8'), retain=False)))
        await mqtt.publish(f'{device_topic}/availability', 'online'.encode('utf8'), retain=False)

        device = {
            'connections': [('bluetooth', self.client.address)],
            'identifiers': self.identifier,
            'manufacturer': 'Adaprox',
            'model': 'Fingerbot Plus',
            'name': self.identifier,
        }
        await mqtt.publish(
            f'{homeassistant_discovery_topic}/button/{self.identifier}/config',
            json.dumps({
                'availability': {
                    'payload_available': 'online',
                    'payload_not_available': 'offline',
                    'topic': f'{device_topic}/availability',
                },
                'command_topic': f'{device_topic}/set/action',
                'device': device,
                'name': device["name"],
                'unique_id': self.identifier,
            }).encode('utf8'))

    async def handleMQTT(self, topic: list[str], data: str) -> None:
        if topic == ['set', 'action'] and data != None:
            return await self.press()

    def __aenter__(self):
        return self.init()

    def __aexit__(self, exc_type, exc_value, traceback):
        return self.finalize()


Device = TuyaFingerBot
