import crypto
import hashlib
from Crypto.Cipher import AES
from struct import pack, unpack
from enum import IntEnum, Enum
import itertools
import typing
import time

# see https://github.com/redphx/poc-tuya-ble-fingerbot/blob/main/pyfingerbot/__init__.py
# and
# https://developer.tuya.com/en/docs/iot/mini-program-integration-documents?id=Ka75d8cadotgh


class TuyaCode(IntEnum):
    FUN_SENDER_DEVICE_INFO = 0
    FUN_SENDER_PAIR = 1
    FUN_SENDER_DPS = 2
    FUN_SENDER_DEVICE_STATUS = 3
    FUN_RECEIVE_TIME1_REQ = 32785
    FUN_RECEIVE_DP = 32769


class TuyaDataType(IntEnum):
    RAW = 0
    BOOLEAN = 1
    INT = 2
    STRING = 3
    ENUM = 4


class TuyaSession():

    def __init__(self, local_key: str) -> None:
        self.login_key = local_key[0:6].encode('ascii')
        self.sn_counter = itertools.count(1)
        self.keys = {4: hashlib.md5(self.login_key).digest()}

    def __getitem__(self, data: int) -> bytes:
        return self.keys[data]

    def is_ready(self):
        return 5 in self.keys

    def set_srand(self, srand: bytes):
        self.keys[5] = hashlib.md5(self.login_key + srand).digest()


def create_message(session: TuyaSession, code: int, data: bytes, security_flag: int = 5, ack_sn: int = 0):
    header = pack('>IIHH', next(session.sn_counter), ack_sn, code, len(data))
    footer = pack('>H', crypto.calc_crc16_modbus(header + data))
    cleartext = crypto.pad_to_multiple(header + data + footer, 16)
    print(f'<7>create_message {cleartext.hex("-")}')
    security_flag_byte = pack('>B', security_flag)
    iv = crypto.get_random_iv()
    encrypted = AES.new(session[security_flag], AES.MODE_CBC, iv).encrypt(cleartext)
    return security_flag_byte + iv + encrypted


def split_packets(message: bytes):
    PROTOCOL_VERSION = 2 << 4
    GATT_MTU = 20
    offset = 0
    for packet_number in itertools.count():
        header = pack('>B', packet_number)
        if packet_number == 0:
            header += pack('>BB', len(message), PROTOCOL_VERSION)
        body = message[offset:offset + GATT_MTU - len(header)]
        yield header + body
        offset += len(body)
        if (offset >= len(message)):
            break


def read_varint(data: bytes, offset: int):
    ret = 0
    i = 0
    for i, b in enumerate(data[offset:offset + 4]):
        ret |= b << (i * 7)
        if b & 0b1000_0000 == 0:
            return ret, i + 1
    return ret, i


async def map_stream(stream, func):
    async for packet in stream:
        yield func(packet)


async def merge_packets(stream: typing.AsyncGenerator[bytes, None]):
    message_length = None
    last_packet_number = None
    buffer = None
    protocol_version = None
    async for packet in stream:
        offset = 0
        packet_number, var_len = read_varint(packet, offset)
        offset += var_len
        if packet_number == 0:
            message_length, var_len = read_varint(packet, offset)
            offset += var_len
            protocol_version = packet[offset] >> 4
            offset += 1
            last_packet_number = None
            buffer = bytearray()
        if last_packet_number == None or packet_number > last_packet_number:
            buffer += packet[offset:]
            last_packet_number = packet_number
            if len(buffer) == message_length:
                yield buffer


def parse_device_info(data: bytes):
    device_version_major, device_version_minor, protocol_version_major, protocol_version_minor, flag, is_bind, srand, hardware_version_major, hardware_version_minor, auth_key = unpack(
        '>BBBBBB6sBB32s', data[:46])
    assert protocol_version_major > 2
    return {
        'device_version': f'{device_version_major}.{device_version_minor}',
        'protocol_version': f'{protocol_version_major}.{protocol_version_minor}',
        'flag': flag,
        'is_bind': is_bind,
        'srand': srand
    }


def parse_message(message: bytes, session: TuyaSession, update_session=True):
    security_flag = message[0]
    iv = message[1:17]
    encrypted = message[17:]
    cleartext = AES.new(session[security_flag], AES.MODE_CBC, iv).decrypt(encrypted)
    sn, ack_sn, code, length = unpack('>IIHH', cleartext[:12])
    data = cleartext[12:12 + length]
    ret = {'code': code, 'data': data}
    try:
        ret['code'] = TuyaCode(code)
    except ValueError:
        pass
    if ret['code'] == TuyaCode.FUN_SENDER_DEVICE_INFO:
        ret |= parse_device_info(data)
        if update_session:
            session.set_srand(ret['srand'])
            ret['update_session'] = True
    return ret


def create_device_info_request(session: TuyaSession):
    return create_message(session=session, code=TuyaCode.FUN_SENDER_DEVICE_INFO, data=bytes(), security_flag=4)


def create_pair_request(session: TuyaSession, uuid: bytes, device_id: bytes):
    ''' uuid: tuya{12-char-hex} device_id: {16-char-word} '''
    data = crypto.pad_to_multiple(uuid + session.login_key + device_id, 44)
    return create_message(session=session, code=TuyaCode.FUN_SENDER_PAIR, data=data, security_flag=5)


def create_time_message(session: TuyaSession):
    ''' WARN: this API supports a fixed timezone offset only, no DST '''
    data = pack('>13sh', bytes(str(time.time_ns()), 'ascii'), -time.timezone // 36)
    return create_message(session=session, code=TuyaCode.FUN_RECEIVE_TIME1_REQ, data=data, security_flag=5)


def create_command_request(session: TuyaSession, commands: list):
    data = bytearray()
    for key, value, in commands:
        data += pack('>B', int(key))
        if type(value) == bool:
            data += pack('>BBB', TuyaDataType.BOOLEAN, 1, int(value))
        elif type(value) == int:
            data += pack('>BBI', TuyaDataType.INT, 4, value)
        elif type(value) == str:
            data += pack('>BB', TuyaDataType.STRING, len(value)) + value.encode('utf-8')
        elif type(value) == Enum:
            data += pack('>BBB', TuyaDataType.ENUM, 1, int(value))
        elif type(value) == bytes:
            data += value
    return create_message(session=session, code=TuyaCode.FUN_SENDER_DPS, data=data, security_flag=5)
