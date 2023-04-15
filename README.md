yet another Bluetooth Low Energy to MQTT bridge (like zigbee2mqtt).

Supported devices:
- [AM43 Smart Control Automatic Chain Blinds Drive Motor](https://www.a-okmotor.com/am43-smart-control-automatic-chain-blinds-drive-motor_p31.html) (also in various other names)
- [Adaprox Fingerbot](https://www.adaprox.io/products/fingerbot-plus-1?variant=40425967812813) (also in various other names)

user: [config readme](./config/README.md)

developer: [device readme](./device/README.md)

# Try it out!
## Prerequisite

ble2mqtt is tested with Python 3.9. It should support newer versions but I didn't test. You will also need git.

## Install dependencies

```bash
pip3 install --upgrade bleak==0.19.5 PyYAML==5.4.1 amqtt==0.10.1 furl==2.1.3 pyee==9.0.4 pycryptodome==3.16.0
```

## Clone the repository
```bash
git clone https://github.com/liqi0816/ble2mqtt
```

## Write config
```yaml
homeassistant: true
mqtt:
  base_topic: homeassistant
  server: mqtt://127.0.1.1:1883
controller:
  address: null
  capacity: 6
devices:
  '01:02:03:04:05:06':
    type: am43
  '01:02:03:04:05:07':
    type: am43
  '01:02:03:04:05:08':
    type: tuya.fingerbot
    device_id: abc123456
    uuid: tuya1234567890
    local_key: abc123456
    down_percent: 80
```

## Run the program
```bash
cd ble2mqtt
python3 main.py --config [path-to-config.yaml]
```
