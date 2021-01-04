import pyee

class BaseDevice(pyee.BaseEventEmitter):
    async def open(self):
        raise NotImplementedError()

    async def close(self):
        raise NotImplementedError()

    async def bindMQTT(self, mqtt, base_topic):
        raise NotImplementedError()

    async def handleMQTT(self, topic, message):
        raise NotImplementedError()

Device = BaseDevice
