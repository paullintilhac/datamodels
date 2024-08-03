#!/bin/bash
cd datamodels
sudo apt install nano
sudo apt install htop
pip install fastargs terminaltables
cd parallel-20240622
./configure && make
make install
cd ..
ls
sudo apt update && sudo apt install -y --no-install-recommends libopencv-dev libturbojpeg-dev
sudo pip install mosaicml ffcv numba opencv-python
pip install cupy-cuda12x
cd rclone-*-linux-amd64
sudo cp rclone /usr/bin/
sudo chown root:root /usr/bin/rclone
sudo chmod 755 /usr/bin/rclone
cd ..