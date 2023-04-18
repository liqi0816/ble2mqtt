#!/bin/bash

python_version=3.10

mkdir -p ${PWD}/conda
mkdir -p ${PWD}/app


systemd-run --unit=conda-install --collect --wait --pty --pipe \
    --property=RuntimeDirectory=conda-install \
    --property=RootDirectory=/run/conda-install \
    --property=MountAPIVFS=yes \
    --property=PrivateTmp=yes \
    --property=Environment="HOME=/run/conda-install" \
    --property=BindPaths="${PWD}/app:/app" \
    --property=BindPaths="${PWD}/conda:/conda" \
    --property=BindReadOnlyPaths=/run/systemd/resolve:/etc \
    --property=BindReadOnlyPaths="/lib /lib32 /lib64 /bin /sbin" \
    /bin/bash -c "
    curl --insecure --location https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh --output /run/conda-install/conda_scaffold.sh
    bash /run/conda-install/conda_scaffold.sh -u -b -p /conda
    /conda/bin/conda install --yes python=${python_version} git
    /conda/bin/git clone https://github.com/liqi0816/ble2mqtt /app
    /conda/bin/pip install --no-cache-dir --upgrade bleak pyyaml furl pyee pip pycryptodome 'amqtt>=0.11.0b1'
    "

cp ${PWD}/app/ble2mqtt.service /etc/systemd/system/ble2mqtt.service
systemctl daemon-reload
systemctl restart ble2mqtt
systemctl status ble2mqtt
