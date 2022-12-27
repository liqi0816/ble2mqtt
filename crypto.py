import collections.abc
import secrets


def calc_xor_checksum(data: collections.abc.Iterable[int]):
    checksum = 0
    for byte in data:
        checksum ^= byte
    return checksum


def calc_crc16_modbus(data: collections.abc.Iterable[int]):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte & 0xFF
        for _ in range(8):
            tmp = crc & 0x0001
            crc >>= 1
            if tmp:
                crc ^= 0xA001
    return crc


def get_random_iv():
    return secrets.token_bytes(16)


def pad_to_multiple(data: collections.abc.Iterable[int], length: int):
    data = bytearray(data)
    while len(data) % length:
        data += b'\x00'
    return bytes(data)
