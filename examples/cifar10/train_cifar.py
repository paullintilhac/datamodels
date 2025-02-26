from argparse import ArgumentParser
from typing import List
import time
import numpy as np
from tqdm import tqdm

import torch as ch
from torch.cuda.amp import GradScaler, autocast
from torch.nn import CrossEntropyLoss
from torch.optim import SGD, lr_scheduler
import torchvision
import argparse
from fastargs import get_current_config, Param, Section
from fastargs.decorators import param

from ffcv.fields.decoders import IntDecoder, SimpleRGBImageDecoder
from ffcv.loader import Loader, OrderOption
from ffcv.pipeline.operation import Operation
from ffcv.transforms import RandomHorizontalFlip, Cutout, \
    RandomTranslate, Convert, ToDevice, ToTensor, ToTorchImage
from ffcv.transforms.common import Squeeze

Section('training', 'Hyperparameters').params(
    lr=Param(float, 'The learning rate to use', default=0.5),
    epochs=Param(int, 'Number of epochs to run for', default=25),
    lr_peak_epoch=Param(int, 'Peak epoch for cyclic lr', default=5),
    batch_size=Param(int, 'Batch size', default=512),
    momentum=Param(float, 'Momentum for SGD', default=0.9),
    weight_decay=Param(float, 'l2 weight decay', default=5e-4),
    label_smoothing=Param(float, 'Value of label smoothing', default=0.1),
    num_workers=Param(int, 'The number of workers', default=1),
    lr_tta=Param(bool, 'Test time augmentation by averaging with horizontally flipped version', default=True)
)
file_prefix = "/dartfs/rc/lab/C/CybenkoG/cifar-ffcv"
Section('data', 'data related stuff').params(
    train_dataset=Param(str, '.dat file to use for training', 
        default=file_prefix+ '/cifar_train.beton'),
    val_dataset=Param(str, '.dat file to use for validation', 
        default=file_prefix+'/cifar_val.beton'),
)

@param('data.train_dataset')
@param('data.val_dataset')
@param('training.batch_size')
@param('training.num_workers')
def make_dataloaders(train_dataset=None, val_dataset=None, batch_size=None, num_workers=None, mask=None):
    paths = {
        'train': train_dataset,
        'test': val_dataset,
        'superset': val_dataset,
    }

    start_time = time.time()
    CIFAR_MEAN = [125.307, 122.961, 113.8575]
    CIFAR_STD = [51.5865, 50.847, 51.255]
    loaders = {}

    for name in ['train', 'test','superset']:
        label_pipeline: List[Operation] = [IntDecoder(), ToTensor(), ToDevice(ch.device("cuda:0")), Squeeze()]
        image_pipeline: List[Operation] = [SimpleRGBImageDecoder()]
        if name in ['train','superset']:
            image_pipeline.extend([
                RandomHorizontalFlip(),
                RandomTranslate(padding=2, fill=tuple(map(int, CIFAR_MEAN))),
                Cutout(4, tuple(map(int, CIFAR_MEAN))),
            ])
        image_pipeline.extend([
            ToTensor(),
            ToDevice(ch.device("cuda:0"), non_blocking=True),
            ToTorchImage(),
            Convert(ch.float16),
            torchvision.transforms.Normalize(CIFAR_MEAN, CIFAR_STD),
        ])
        
        ordering = OrderOption.RANDOM if name == 'train' else OrderOption.SEQUENTIAL
        print("len of mask: " + str(len(mask)))
        loaders[name] = Loader(paths[name], indices=(mask if name == 'train' else None),
                               batch_size=batch_size, num_workers=num_workers,
                               order=ordering, drop_last=(name == 'train'),
                               pipelines={'image': image_pipeline, 'label': label_pipeline})
    print("length of train loader: " + str(len(loaders['superset'])))
    print("length of train loader: " + str(len(loaders['train'])))
    print("length of train loader: " + str(len(loaders['test'])))

    return loaders

# Model (from KakaoBrain: https://github.com/wbaek/torchskeleton)
class Mul(ch.nn.Module):
    def __init__(self, weight):
       super(Mul, self).__init__()
       self.weight = weight
    def forward(self, x): return x * self.weight

class Flatten(ch.nn.Module):
    def forward(self, x): return x.view(x.size(0), -1)

class Residual(ch.nn.Module):
    def __init__(self, module):
        super(Residual, self).__init__()
        self.module = module
    def forward(self, x): return x + self.module(x)

def conv_bn(channels_in, channels_out, kernel_size=3, stride=1, padding=1, groups=1):
    return ch.nn.Sequential(
            ch.nn.Conv2d(channels_in, channels_out, kernel_size=kernel_size,
                         stride=stride, padding=padding, groups=groups, bias=False),
            ch.nn.BatchNorm2d(channels_out),
            ch.nn.ReLU(inplace=True)
    )

def construct_model():
    num_class = 10
    model = ch.nn.Sequential(
        conv_bn(3, 64, kernel_size=3, stride=1, padding=1),
        conv_bn(64, 128, kernel_size=5, stride=2, padding=2),
        Residual(ch.nn.Sequential(conv_bn(128, 128), conv_bn(128, 128))),
        conv_bn(128, 256, kernel_size=3, stride=1, padding=1),
        ch.nn.MaxPool2d(2),
        Residual(ch.nn.Sequential(conv_bn(256, 256), conv_bn(256, 256))),
        conv_bn(256, 128, kernel_size=3, stride=1, padding=0),
        ch.nn.AdaptiveMaxPool2d((1, 1)),
        Flatten(),
        ch.nn.Linear(128, num_class, bias=False),
        Mul(0.2)
    )
    model = model.to(memory_format=ch.channels_last).cuda()
    return model

@param('training.lr')
@param('training.epochs')
@param('training.momentum')
@param('training.weight_decay')
@param('training.label_smoothing')
@param('training.lr_peak_epoch')
def train(model, loaders, lr=None, epochs=None, label_smoothing=None,
          momentum=None, weight_decay=None, lr_peak_epoch=None):
    opt = SGD(model.parameters(), lr=lr, momentum=momentum, weight_decay=weight_decay)
    iters_per_epoch = len(loaders['train'])
    # Cyclic LR with single triangle
    lr_schedule = np.interp(np.arange((epochs+1) * iters_per_epoch),
                            [0, lr_peak_epoch * iters_per_epoch, epochs * iters_per_epoch],
                            [0, 1, 0])
    scheduler = lr_scheduler.LambdaLR(opt, lr_schedule.__getitem__)
    scaler = GradScaler()
    loss_fn = CrossEntropyLoss(label_smoothing=label_smoothing)
    loss = None
    for _ in range(epochs):
        for ims, labs in tqdm(loaders['train']):
            opt.zero_grad(set_to_none=True)
            with autocast():
                out = model(ims)
                loss = loss_fn(out, labs)

            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            scheduler.step()
    print("done training! loss: " +str(loss) )

@param('training.lr_tta')
def evaluate(model, loaders, lr_tta=False):
    model.eval()
    with ch.no_grad():
        all_margins = []
        all_confidences = []
        #accuracies=[]
        i=0
        for ims, labs in tqdm(loaders['superset']):
            i+=1
            with autocast():
                out = model(ims)
                if lr_tta:
                    out += model(ch.fliplr(ims))
                    out /= 2
                #using correct class margins, not confidences
                #print("using logits")
                #prediction = ch.argmax(out[ch.arange(out.shape[0]), :],1)
                #accuracy = (prediction == labs)
                class_logits = out[ch.arange(out.shape[0]), labs].clone()
                all_confidences.append(class_logits.cpu())
                class_logits = class_logits.clone()
                out[ch.arange(out.shape[0]), labs] = -1000
                next_classes = out.argmax(1)
                class_logits -= out[ch.arange(out.shape[0]), next_classes]
                all_margins.append(class_logits.cpu())
                #accuracies.append(accuracy.cpu())
        all_margins = ch.cat(all_margins)
        all_confidences = ch.cat(all_confidences)

        #accuracies = ch.cat(accuracies).long().float()
        #print("head of accuracies: " + str(accuracies[:5]))
        #print("mean accuracy: " + str(ch.mean(accuracies)))
        #print("all_margins shape: " + str(all_margins.shape))
        #print('Average margin:', all_margins.mean())
        return all_margins.numpy(),all_confidences.numpy()
def main(index, logdir):
    config = get_current_config()
    print("device count: " + str(ch.cuda.device_count()))
    parser = ArgumentParser(description='Fast CIFAR-10 training')
    config.augment_argparse(parser)
    # Also loads from args.config_path if provided
    config.collect_argparse_args(parser)
    config.validate(mode='stderr')
    config.summary()

    mask = (np.random.rand(50_000) > 0.5)

    ones = np.ones(10000)
    zeros =  np.zeros(40000)
    print("ones shape: " + str(ones.shape) + ", zeros: " + str(zeros))
    subset_mask = np.concatenate((ones,zeros))
    print("subset mask dim: " + str(subset_mask.shape))
    mask=np.multiply(mask,subset_mask)
    loaders = make_dataloaders(mask=np.nonzero(mask)[0])
    model = construct_model()
    train(model, loaders)
    margins,confidences = evaluate(model, loaders)
    print(mask.shape, margins.shape, confidences.shape)
    return {
        'masks': mask,
        'margins': margins,
        "confidences": confidences
    }
