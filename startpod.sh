#!/bin/bash

sudo podman run -it --rm --network=host --volume=/opt/ble2mqtt:/opt/ble2mqtt python:3.8 bash
cd /opt/ble2mqtt
# shopt -s extglob
# rm -r !('___my')
python3 -m venv --copies /opt/ble2mqtt
source bin/activate
cp -r /usr/local/lib/python3.8/distutils /opt/ble2mqtt/bin
pip install bleak pyyaml hbmqtt
export PYTHONPATH=/opt/ble2mqtt/bin
