import yaml
import asyncio
import hbmqtt.mqtt.constants
import hbmqtt.client
import furl
import bluetooth
import importlib
import contextlib
import argparse


@contextlib.asynccontextmanager
async def get_devices_reg(configuration):
    devices_reg = {}
    cache = bluetooth.Cache(configuration['controller'].get('capacity'))
    try:
        for address in configuration['devices']:
            device_type = configuration['devices'][address]['type']
            device_config = configuration['devices'][address].get('config', {})
            device = importlib.import_module(f'device.{device_type}').Device(address, cache, **device_config)
            devices_reg[device.identifier] = device
            if hasattr(device, 'init'):
                await device.init()
        yield devices_reg
    finally:
        await asyncio.gather(*(device.finalize() for device in devices_reg.values() if hasattr(device, 'finalize')))


@contextlib.asynccontextmanager
async def get_mqtt(configuration):
    mqtt = hbmqtt.client.MQTTClient(client_id=configuration['mqtt'].get('client_id'), config={'default_retain': True})
    try:
        await mqtt.connect(furl.furl(configuration['mqtt']['server']).set(
            username=str(configuration['mqtt'].get('user')),
            password=str(configuration['mqtt'].get('password')),
        ).url)
        base_topic = configuration['mqtt']['base_topic']
        await mqtt.subscribe([(f'{base_topic}/#', hbmqtt.mqtt.constants.QOS_0)])
        yield mqtt
    finally:
        await mqtt.disconnect()


async def main():
    parser = argparse.ArgumentParser(description='A naive mimic of zigbee2mqtt for bluetooth with python')
    parser.add_argument('-c', '--config', default='config/configuration.yaml', help='configuration.yaml location')
    with open(parser.parse_args().config) as config:
        configuration = yaml.safe_load(config)
    async with get_devices_reg(configuration) as devices_reg, get_mqtt(configuration) as mqtt:
        base_topic = configuration['mqtt']['base_topic']
        await asyncio.gather(*(device.bindMQTT(mqtt=mqtt, device_topic=f'{base_topic}/{identifier}')
                               for identifier, device in devices_reg.items()))
        while True:
            message = await mqtt.deliver_message()
            base_topic, identifier, *topic = message.topic.split('/')
            data = message.data.decode('utf8')
            if identifier in devices_reg:
                asyncio.create_task(devices_reg[identifier].handleMQTT(topic=topic, data=data))

asyncio.run(main())
