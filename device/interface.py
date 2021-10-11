from __future__ import annotations
import hbmqtt.client
import abc


class BaseDevice(abc.ABC):
    @property
    @abc.abstractmethod
    def identifier(self) -> str:
        raise NotImplementedError()

    @abc.abstractmethod
    async def bindMQTTPublish(self, mqtt: hbmqtt.client.MQTTClient, device_topic: str, homeassistant_discovery_topic: str = None) -> None:
        '''
        bind the mqtt client for publishing state updates.
        should not mqtt.subscribe here since it may be handled elsewhere.
        if given homeassistant_discovery_topic, also setup homeassistant discovery.
        '''
        raise NotImplementedError()

    @abc.abstractmethod
    async def handleMQTTMessage(self, topic: list[str], data: str) -> None:
        '''
        handle incoming mqtt message.
        topic is already split to parts.

        for backward compability the implementation should try to accept two patterns:

            1. topic='set', data='{state:'OPEN'}'
            2. topic='set/state', data='OPEN'
        '''
        raise NotImplementedError()

    @abc.abstractmethod
    async def __aenter__(self) -> 'BaseDevice':
        '''
        any initialization. not required method, but suggested.
        '''
        pass

    @abc.abstractmethod
    async def __aexit__(self, exc_type, exc_value, traceback):
        '''
        any clean up. not required method, but suggested.
        '''
        pass


Device = BaseDevice
