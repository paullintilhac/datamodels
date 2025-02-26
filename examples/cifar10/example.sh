#!/bin/bash

set -e
tmp_dir=./tmp/$RANDOM
mkdir -p $tmp_dir
echo "Job dir: ${tmp_dir}"
#conda activate ffcv2

# first make the store
# if you look at spec.json, we are training 10 models!
python -m datamodels.training.initialize_store \
    --logging.logdir=${tmp_dir} \
    --logging.spec=examples/cifar10/spec.json

# now we run the workers, all with the same python invocation
#   but parallelized across 8 different workers, one for each GPU in this example.
# seq 0 9 generates 0 through 9 separated by newlines (10 jobs total, same as our spec expects)
# parallel parses each of these separately and sends them to the python invocation
# there are 8 gpus available so we use 8 jobs and assign each a gpu according to the
#   index number (i.e. the current `seq` output) modulo 8

seq 0 9999 | parallel -k --lb -j1 CUDA_VISIBLE_DEVICES='$(({%} % 1))' \

 python -m datamodels.training.worker \
    --worker.index={} \
    --worker.main_import=examples.cifar10.train_cifar \
    --worker.logdir=${tmp_dir}

echo "\n\n"
echo "jobs done! Data in: ${tmp_dir}:"
echo "> ${tmp_dir}/masks.npy: shape (10, 50000) bool masks matrix; M[i,j]=true if training example j in train set for model i"
echo "> ${tmp_dir}/margins.npy: shape (10, 10000) float16 margins matrix; M[i,j]=model i margin on test example j"
echo "> ${tmp_dir}/_completed.npy: shape (10,) bool completion matrix; M[i] = was model i completed"
