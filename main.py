import yaml
import asyncio
import hbmqtt.client, hbmqtt.mqtt.constants
import furl

configuration = yaml.safe_load(open('data/configuration.yaml'))

# 1. setup mqtt client
async def mqtt():
    client = hbmqtt.client.MQTTClient(client_id=configuration['mqtt'].get('client_id'))
    await client.connect(furl.furl(configuration['mqtt']['server']).set(
        username=str(configuration['mqtt'].get('user')),
        password=str(configuration['mqtt'].get('password')),
    ).url)
    await client.subscribe([(f"{configuration['mqtt']['base_topic']}/#", hbmqtt.mqtt.constants.QOS_0)])
    while True:
        message = await client.deliver_message()
        breakpoint
    



asyncio.run(mqtt())

# 2. setup device handlers
