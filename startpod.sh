#!/bin/bash

# sudo git clean --force -dX

if command -v python3; then
    python_version=$(python3 --version 2>&1)
elif command -v python; then
    python_version=$(python --version 2>&1)
else
    : ${python_version?neither python 2 or 3 detected}
fi
python_version=$(grep --only-matching '[2-3]\.[0-9][0-9]*\.[0-9][0-9]*' <<< $python_version)

miniconda_tmp=$(mktemp -p /tmp -d)
curl --insecure --location https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh --output "$miniconda_tmp"/conda_scaffold.sh
bash "$miniconda_tmp"/conda_scaffold.sh -b -p "$miniconda_tmp"/conda_dir

ble2mqtt_opt_dir="${ble2mqtt_opt_dir:-/opt/ble2mqtt}"
"$miniconda_tmp"/conda_dir/bin/conda create --yes --name ble2mqtt python="$python_version"
"$miniconda_tmp"/conda_dir/envs/ble2mqtt/bin/pip install --upgrade bleak pyyaml hbmqtt furl pyee pip --target "$ble2mqtt_opt_dir" --no-cache-dir
