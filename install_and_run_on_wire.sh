#!/bin/bash
git clone https://github.com/paullintilhac/datamodels.git
cd datamodels
git checkout wire
pip install fastargs terminaltables
wget http://ftp.gnu.org/gnu/parallel/parallel-latest.tar.bz2
tar xjf parallel-latest.tar.bz2
cd parallel-20240622
./configure && make
make install
cd ..
sudo apt update && sudo apt install -y --no-install-recommends libopencv-dev libturbojpeg-dev
sudo pip install mosaicml ffcv numba opencv-python
pip install cupy-cuda12x
curl -O https://downloads.rclone.org/rclone-current-linux-amd64.zip
unzip rclone-current-linux-amd64.zip
cd rclone-*-linux-amd64
sudo cp rclone /usr/bin/
sudo chown root:root /usr/bin/rclone
sudo chmod 755 /usr/bin/rclone
rclone config
mkdir tmp
rclone copy temfom:tmp tmp
rclone copy temfom:files files
./examples/cifar10/example.sh &> log_0.txt & rclone sync tmp temfom:tmp
