#!/bin/bash

# sudo git clean --force -dX

sudo podman run -it --rm --network=host --volume=/opt/ble2mqtt:/opt/ble2mqtt python:3.8 bash
# sudo podman run -it --rm --network=host --volume=/opt/ble2mqtt:/opt/ble2mqtt homeassistant/home-assistant:latest bash
# apk add build-base
cd /opt/ble2mqtt
python3 -m venv --copies /opt/ble2mqtt
source bin/activate
cp -r /usr/local/lib/python3.8/distutils /opt/ble2mqtt/lib/python3.8/site-packages
pip install --upgrade bleak pyyaml hbmqtt furl pyee pip
pip install --upgrade autopep8

cd /opt/ble2mqtt
# python3 -m venv --copies /opt/ble2mqtt
export PYTHONPATH=/opt/ble2mqtt/lib/python3.8/site-packages
