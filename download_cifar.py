from typing import List

import torch as ch
import torchvision

from ffcv.fields import IntField, RGBImageField
from ffcv.fields.decoders import IntDecoder, SimpleRGBImageDecoder
from ffcv.loader import Loader, OrderOption
from ffcv.pipeline.operation import Operation
from ffcv.transforms import RandomHorizontalFlip, Cutout, \
    RandomTranslate, Convert, ToDevice, ToTensor, ToTorchImage
from ffcv.transforms.common import Squeeze
from ffcv.writer import DatasetWriter
datasets = {
    'train': torchvision.datasets.CIFAR10('/dartfs/rc/lab/C/CybenkoG/cifar-ffcv2', train=True, download=True),
    'test': torchvision.datasets.CIFAR10('/dartfs/rc/lab/C/CybenkoG/cifar-ffcv2', train=False, download=True)
}

train = datasets['train']
print("train: " + str(type(train[0])))
print("len train: " + str(len(train)))
print("train[0]: " + str(train[0]))

for (name, ds) in datasets.items():
    writer = DatasetWriter(f'/dartfs/rc/lab/C/CybenkoG/cifar-ffcv/cifar_{name}.beton', {
        'image': RGBImageField(),
        'label': IntField()
    })
    writer.from_indexed_dataset(ds)
