
```yaml
homeassistant: (not implement yet)
mqtt:
  base_topic: Required, MQTT base topic for ble2mqtt MQTT messages
  server: Required, MQTT server URL
controller:
  address: (not implement yet)
  capacity: max concurrent connection supported on the bluetooth controller
devices:
  # device MAC address
  '00:01:02:03:04:05':
    type: Required, device type 
    # can add device specific config here
    config_extra_1: some value
```