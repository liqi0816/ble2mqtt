import yaml
import asyncio
import amqtt.mqtt.constants
import amqtt.client
import furl
import bluetooth
import importlib
import contextlib
import argparse
from device.interface import BaseDevice


@contextlib.asynccontextmanager
async def get_devices_reg(configuration):
    devices_reg: dict[str, BaseDevice] = {}
    cache = bluetooth.Cache(configuration['controller'].get('capacity'))
    async with contextlib.AsyncExitStack() as stack:
        for address in configuration['devices']:
            client = bluetooth.Client(address, cache)
            device_type = configuration['devices'][address]['type']
            device_config = dict(configuration['devices'][address])
            device_config.pop('type')
            device: BaseDevice = importlib.import_module(f'device.{device_type}').Device(client, **device_config)
            devices_reg[device.identifier] = await stack.enter_async_context(device)
        yield devices_reg


@contextlib.asynccontextmanager
async def get_mqtt(configuration):
    mqtt = amqtt.client.MQTTClient(client_id=configuration['mqtt'].get('client_id'), config={'default_retain': True})
    try:
        await mqtt.connect(
            furl.furl(configuration['mqtt']['server']).set(
                username=str(configuration['mqtt'].get('user')),
                password=str(configuration['mqtt'].get('password')),
            ).url)
        base_topic = configuration['mqtt']['base_topic']
        await mqtt.subscribe([(f'{base_topic}/#', amqtt.mqtt.constants.QOS_0)])
        yield mqtt
    finally:
        # for any will messages
        await asyncio.sleep(1)
        await mqtt.disconnect()


async def main():
    parser = argparse.ArgumentParser(description='A naive mimic of zigbee2mqtt for bluetooth with python')
    parser.add_argument('-c', '--config', default='config/configuration.yaml', help='configuration.yaml location')
    with open(parser.parse_args().config) as config:
        configuration = yaml.safe_load(config)
        base_topic = configuration['mqtt']['base_topic']
        homeassistant_discovery_topic = 'homeassistant'
        async with get_mqtt(configuration) as mqtt, get_devices_reg(configuration) as devices_reg:
            print(f'<6>initialized with {len(devices_reg)} devices')
            await asyncio.gather(*(device.bindMQTT(
                mqtt=mqtt,
                device_topic=f'{base_topic}/{identifier}',
                homeassistant_discovery_topic=homeassistant_discovery_topic,
            ) for identifier, device in devices_reg.items()))
            while True:
                message = await mqtt.deliver_message()
                base_topic, identifier, *topic = message.topic.split('/')
                data = message.data.decode('utf8')
                if identifier in devices_reg:
                    asyncio.create_task(devices_reg[identifier].handleMQTT(topic=topic, data=data))


asyncio.run(main())
