#!/bin/bash

#SBATCH --account=temfom0  # Specify the account to charge

#SBATCH --job-name=my_job  # Job name

#SBATCH --output=jobs/my_job_%j.out  # Standard output and error log

#SBATCH --error=jobs/my_job_%j.err  
#SBATCH --time=80:00:00  # Time limit hrs:min:sec

#SBATCH --partition=gpuq  # Specify the partition to submit to
#SBATCH --gres=gpu:2
echo $(hostname -s)

source activate ffcv2
nvcc --version
echo conda env:

./examples/cifar10/example.sh
