import amqtt.client
import abc


class BaseDevice(abc.ABC):

    @property
    @abc.abstractmethod
    def identifier(self) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    async def __aenter__(self) -> 'BaseDevice':
        '''
        Will be called right after __init__.
        Async initializer.
        '''
        pass

    @abc.abstractmethod
    async def __aexit__(self, exc_type, exc_value, traceback):
        '''
        Will be called right after removal from device registry.
        Async finalizer.
        '''
        pass

    @abc.abstractmethod
    async def bindMQTT(self, mqtt: amqtt.client.MQTTClient, device_topic: str, homeassistant_discovery_topic: str = None) -> None:
        '''
        Will be called once the mqtt client is ready.
        Add `mqtt.publish` as a device notification listener here.
        This function register all device->mqtt messages while `handleMQTT` register mqtt->device ones.
        If homeassistant_discovery_topic is set, this function should also publish discovery message.
        '''
        raise NotImplementedError()

    @abc.abstractmethod
    async def handleMQTT(self, topic: list[str], data: str) -> None:
        '''
        Will be called when a message for this device arrives.
        Call `bluetooth.send(command)` here.
        `topic` is already a list of string.
        This function register all mqtt->device messages while `bindMQTT` register device->mqtt ones.
        For backward compability the implementation should try to accept two patterns:
            1. topic='set', data='{state:'OPEN'}'
            2. topic='set/state', data='OPEN'
        '''
        raise NotImplementedError()


Device = BaseDevice
