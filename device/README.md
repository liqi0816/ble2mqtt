This folder contains device specific commands/handlers

# export

- file/module name should match `type` in the configuration file.
- every file/module should exports a `Device` class which will be explained later

When resolving devices, main.py will use `importlib.import_module(f'device.{device_type}').Device(client, **device_config)`

# interface

the `Device` class should implement the interface specified in [interface.py](./interface.py)
