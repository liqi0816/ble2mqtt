from __future__ import annotations
import asyncio
import bluetooth
import json
from . import util


class TuyaFingerBot(bluetooth.EventEmitter):
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

    def __init__(self, client: bluetooth.Client, device_id: str, uuid: str, local_key: str, down_percent: int = 80, identifier=''):
        super().__init__()
        self.client = client
        self.identifier = identifier or f'tuya_fingerbot_{client.address.replace(":", "").lower()}'
        self.device_id = device_id.encode('ascii')
        self.uuid = uuid.encode('ascii')
        self.local_key = local_key
        self.down_percent = down_percent
        self.session = util.TuyaSession(self.local_key)

    async def __aenter__(self):
        await self.client.__aenter__()
        self.client.event.on('disconnect', lambda: setattr(self, 'session', util.TuyaSession(self.local_key)))
        asyncio.create_task(self.listen_notification())
        self.emit('init')
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.client.__aexit__(exc_type, exc_value, traceback)
        self.emit('finalize')

    async def listen_notification(self):
        stream = util.map_stream(self.client.recv_stream_opportunistic(TuyaFingerBot.CHAR_ID['notification']), lambda data: data[1])
        async for message_raw in util.merge_packets(stream):
            message = util.parse_message(message_raw, self.session)
            code = message['code']
            print(f'<7>listen_notification {self.identifier} received {str(code)} {message["data"].hex("-")}')
            if message.get('update_session', False):
                self.emit('update_session')
            elif code == util.TuyaCode.FUN_SENDER_PAIR:
                self.emit('paired')

    async def sync_session(self):
        '''
        Tuya devices will disconnect from their side after a short time.
        On reconnect:
        1. need to redo start_notify
        2. need to get a new session
        '''
        if self.session.is_ready():
            return
        await asyncio.gather(self.once_async('update_session'), self.send_request(util.create_device_info_request(self.session)))
        await asyncio.gather(self.once_async('paired'),
                             self.send_request(util.create_pair_request(self.session, uuid=self.uuid, device_id=self.device_id)))

    async def send_request(self, request: bytes):
        for packet in util.split_packets(request):
            await self.client.send(TuyaFingerBot.CHAR_ID['state'], packet)

    async def press(self):
        await self.sync_session()
        await self.send_request(
            util.create_command_request(self.session, (
                (self.ACTION['MODE'], bytes((util.TuyaDataType.ENUM, 1, 0))),
                (self.ACTION['ARM_DOWN_PERCENT'], self.down_percent),
                (self.ACTION['ARM_UP_PERCENT'], 0),
                (self.ACTION['CLICK_SUSTAIN_TIME'], 0),
                (self.ACTION['CLICK'], True),
            )))

    async def bindMQTT(self, mqtt, device_topic: str, homeassistant_discovery_topic: str = None) -> None:
        self.on('finalize', lambda: asyncio.create_task(mqtt.publish(f'{device_topic}/availability', 'offline'.encode('utf8'), retain=False)))
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
        elif topic == ['ping'] and data != None:
            return await self.sync_session()


Device = TuyaFingerBot
