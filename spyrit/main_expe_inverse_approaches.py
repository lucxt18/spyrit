# %%
from __future__ import print_function, division
import torch
import torch.nn as nn
import torch.optim as optim
from torch.optim import lr_scheduler
import numpy as np
import torchvision
from torchvision import datasets, models, transforms
import argparse
import sys
from pathlib import Path
import scipy.io as sio

from spyrit.learning.model_Had_DCAN import *
from spyrit.learning.nets import *
from spyrit.misc.disp import *
from spyrit.misc.metrics import *

# import tabulate
import os, sys
import warnings

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


# %% Functions to load the experimental Data
def read_mat_data_index(expe_data, nflip, lambda_i=548):
    F_pos = sio.loadmat(expe_data + "_{}_100_pos_data.mat".format(nflip));
    F_neg = sio.loadmat(expe_data + "_{}_100_neg_data.mat".format(nflip));
    F_spectro = F_pos["spec"][0][0][0];
    F_spectro = F_spectro[0, :];
    lambda_indices = np.where(np.abs(F_spectro - lambda_i) < 1);
    num_channel = lambda_indices[0][0];
    F_data_pos = F_pos["F_WT_lambda_pos"];
    F_data_neg = F_neg["F_WT_lambda_neg"];
    F_pos = F_data_pos[:, :, num_channel];
    F_neg = F_data_neg[:, :, num_channel];
    if (2 ** 16 - 1 in F_pos) or (2 ** 16 - 1 in F_neg):
        warnings.warn("Warning, Saturation!", UserWarning)
    F_pos = F_pos.astype("int64");
    F_neg = F_neg.astype("int64");
    return F_pos, F_neg;


def read_mat_data(expe_data, nflip, lambda_min=460, lambda_max=700):
    F_pos = sio.loadmat(expe_data + "_{}_100_pos_data.mat".format(nflip));
    F_neg = sio.loadmat(expe_data + "_{}_100_neg_data.mat".format(nflip));
    F_data_pos = F_pos["F_WT_lambda_pos"];
    F_data_neg = F_neg["F_WT_lambda_neg"];
    F_spectro = F_pos["spec"][0][0][0];
    F_spectro = F_spectro[0, :];
    F_pos = F_data_pos[:, :, F_spectro > lambda_min];
    F_neg = F_data_neg[:, :, F_spectro > lambda_min];
    F_spectro = F_spectro[F_spectro > lambda_min];
    F_pos = F_pos[:, :, F_spectro < lambda_max];
    F_neg = F_neg[:, :, F_spectro < lambda_max];
    F_pos = np.sum(F_pos, axis=2);
    F_pos = F_pos.astype("int64");
    F_neg = np.sum(F_neg, axis=2);
    F_neg = F_neg.astype("int64");
    return F_pos, F_neg;


def read_mat_data_proc(expe_data, nflipi, lamdba_min=460, lambda_max=700):
    F = sio.loadmat(expe_data + "_{}_100_data.mat".format(nflip));
    F_data = F["F_WT_lambda"];
    F_spectro = F["spec"][0][0][0];
    F_spectro = F_spectro[0, :];
    F = F_data[:, :, F_spectro > lamdba_min];
    F_spectro = F_spectro[F_spectro > lamdba_min];
    F = F[:, :, F_spectro < lambda_max];
    F = np.sum(F, axis=2);
    return F;


# warning: K not used!
def load_data_list_index(expe_data, nflip, CR, K, Perm, img_size, num_channel=548):
    even_index = range(0, 2 * CR, 2);
    odd_index = range(1, 2 * CR, 2);
    m_list = [];
    for i in range(len(nflip)):
        F_pos, F_neg = read_mat_data_index(expe_data[i], nflip[i], num_channel);
        F_pos = F_pos;
        F_neg = F_neg;
        f_pos = np.reshape(F_pos, (img_size ** 2, 1));
        f_neg = np.reshape(F_neg, (img_size ** 2, 1));
        f_re_pos = np.dot(Perm, f_pos);
        f_re_neg = np.dot(Perm, f_neg);
        m = np.zeros((2 * CR, 1));
        m[even_index] = f_re_pos[:CR];
        m[odd_index] = f_re_neg[:CR];
        m = torch.Tensor(m);
        m = m.view(1, 1, 2 * CR);
        m = m.to(device);
        m_list.append(m);
    return m_list


def load_data_list(expe_data, nflip, CR, K, Perm, img_size, lambda_min=460, lambda_max=700):
    even_index = range(0, 2 * CR, 2);
    odd_index = range(1, 2 * CR, 2);
    m_list = [];
    for i in range(len(nflip)):
        F_pos, F_neg = read_mat_data(expe_data[i], nflip[i], lambda_min, lambda_max);
        F_pos = 1 / K * F_pos;
        F_neg = 1 / K * F_neg;
        f_pos = np.reshape(F_pos, (img_size ** 2, 1));
        f_neg = np.reshape(F_neg, (img_size ** 2, 1));
        f_re_pos = np.dot(Perm, f_pos);
        f_re_neg = np.dot(Perm, f_neg);
        m = np.zeros((2 * CR, 1));
        m[even_index] = f_re_pos[:CR];
        m[odd_index] = f_re_neg[:CR];
        m = torch.Tensor(m);
        m = m.view(1, 1, 2 * CR);
        m = m.to(device);
        m_list.append(m);
    return m_list


def ground_truth_list_index(expe_data, nflip, H, img_size, num_channel=548):
    gt_list = [];
    max_list = [];
    for i in range(len(nflip)):
        F_pos, F_neg = read_mat_data_index(expe_data[i], nflip[i], num_channel);
        f_pos = np.reshape(F_pos, (img_size ** 2, 1));
        f_neg = np.reshape(F_neg, (img_size ** 2, 1));
        Gt = np.reshape((1 / img_size) * np.dot(H, f_pos - f_neg), (img_size, img_size));
        max_list.append(np.amax(Gt) - np.amin(Gt));
        Gt = 2 * (Gt - np.amin(Gt)) / (np.amax(Gt) - np.amin(Gt)) - 1;
        gt_list.append(Gt);
    return gt_list, max_list


def raw_ground_truth_list_index(expe_data, nflip, H, img_size, num_channel=548):
    gt_list = [];
    for i in range(len(nflip)):
        F_pos, F_neg = read_mat_data_index(expe_data[i], nflip[i], num_channel);
        f_pos = np.reshape(F_pos, (img_size ** 2, 1));
        f_neg = np.reshape(F_neg, (img_size ** 2, 1));
        Gt = np.reshape((1 / img_size) * np.dot(H, f_pos - f_neg), (img_size, img_size));
        gt_list.append(Gt);
    return gt_list


def ground_truth_list(expe_data, nflip, H, img_size, lambda_min=460, lambda_max=700):
    gt_list = [];
    max_list = [];
    for i in range(len(nflip)):
        F_pos, F_neg = read_mat_data(expe_data[i], nflip[i], lambda_min, lambda_max);
        f_pos = np.reshape(F_pos, (img_size ** 2, 1));
        f_neg = np.reshape(F_neg, (img_size ** 2, 1));
        Gt = np.reshape((1 / img_size) * np.dot(H, f_pos - f_neg), (img_size, img_size));
        max_list.append(np.amax(Gt) - np.amin(Gt));
        Gt = 2 * (Gt - np.amin(Gt)) / (np.amax(Gt) - np.amin(Gt)) - 1;
        gt_list.append(Gt);
    return gt_list, max_list


def net_list(img_size, CR, Mean_had, Cov_had, net_arch, N0_list, sig, denoise, H, suffix, model_root):
    net_type = ['c0mp', 'comp', 'pinv', 'free']
    list_nets = [];
    for N0 in N0_list:
        recon_type = "";
        if N0 == 0:
            train_type = ''
        else:
            train_type = '_N0_{:g}_sig_{:g}'.format(N0, sig)
            if denoise:
                recon_type += "_Denoi";
        # - training parameters
        title = model_root + 'NET_' + net_type[net_arch] + train_type + recon_type + suffix;
        if N0 == 0:
            model = compNet(img_size, CR, Mean_had, Cov_had, net_arch, H)
        else:
            if denoise:
                model = DenoiCompNet(img_size, CR, Mean_had, Cov_had, net_arch, N0, sig, H);
            else:
                model = noiCompNet(img_size, CR, Mean_had, Cov_had, net_arch, N0, sig, H);
        model = model.to(device);
        load_net(title, model, device);
        list_nets.append(model);
    return list_nets;


def simulated_noisy_images(gt_list, max_list, K, H):
    gt_index = max_list.index(max(max_list));
    GT = gt_list[gt_index];
    N = GT.shape[0];
    H_pos = np.zeros(H.shape);
    H_neg = np.zeros(H.shape);
    H_pos[H > 0] = N * H[H > 0];
    H_neg[H < 0] = -N * H[H < 0];
    simu_list = [];
    for i in range(len(gt_list)):
        if i != gt_index:
            f_noi = simulated_measurement(GT, max_list[i] / K, H_pos, H_neg, N, H)
        else:
            f_noi = GT;
        simu_list.append(f_noi)
    return simu_list


def simulated_measurement(GT, N0, H_pos, H_neg, N, H):
    f = N0 * np.reshape(((GT - np.amin(GT)) / (np.amax(GT) - np.amin(GT))), (N ** 2, 1));
    m_pos = np.dot(H_pos, f);
    m_neg = np.dot(H_neg, f);
    m_pos += np.multiply(np.sqrt(m_pos), np.random.normal(0, 1, size=m_pos.shape));
    m_neg += np.multiply(np.sqrt(m_neg), np.random.normal(0, 1, size=m_neg.shape));
    m_noi = m_pos - m_neg;
    f_noi = np.reshape((1 / N) * np.dot(H, m_pos - m_neg), (N, N));
    f_noi = 2 * (f_noi - np.amin(f_noi)) / (np.amax(f_noi) - np.amin(f_noi)) - 1;
    return f_noi;


def normalize(Img, a, b):
    return (a - b) * (Img - np.amin(Img)) / (np.amax(Img) - np.amin(Img)) + b;


def batch_flipud(vid):
    outs = vid;
    for i in range(vid.shape[1]):
        outs[0, i, 0, :, :] = np.flipud(vid[0, i, 0, :, :]);
    return outs;


# Defining functions to improve the metrics
def double_param_reg(f, g):
    N = f.shape[-2] * f.shape[-1];
    f_vec = np.reshape(f[0, 0, :, :], (N, 1));
    g_vec = np.reshape(g[0, 0, :, :], (N, 1));
    f_mean = np.mean(f_vec);
    g_mean = np.mean(g_vec);
    g_norm = np.dot(np.transpose(g_vec), g_vec);
    g_f = np.dot(np.transpose(g_vec), f_vec);
    a = (g_f - N * f_mean * g_mean) / (g_norm - g_mean ** 2);
    b = (f_mean * g_norm - g_mean * g_f) / (g_norm - g_mean ** 2);
    return a * g + b;


def single_param_reg(f, g):
    N = f.shape[-2] * f.shape[-1];
    f_vec = np.reshape(f[0, 0, :, :], (N, 1));
    g_vec = np.reshape(g[0, 0, :, :], (N, 1));
    g_norm = np.dot(np.transpose(g_vec), g_vec);
    g_f = np.dot(np.transpose(g_vec), f_vec);
    a = (g_f) / (g_norm);
    return a * g;


from scipy.sparse.linalg import aslinearoperator


# from bm3d import bm3d, BM3DProfile


def diag(y):
    n = y.shape[0];
    D = np.zeros((n, n));
    D[np.diag_indices(n)] = np.reshape(y, (n,));
    return D;


def Diag(A):
    a, b = A.shape;
    n = min(a, b);
    d = np.reshape(A[np.diag_indices(n)], (n, 1));
    return d;

########################
# Acquisition Parameters
########################
img_size = 64;  # Height / width dimension
CR = 1024;  # Number of patterns
K = 1.6;  # Normalisation constant
C = 1070;
s = 55;
N0 = 10  # maximum photons/pixel in training stage
sig = 0.0  # std of maximum photons/pixel

precompute_root = '/home/licho/Documentos/Stage/Codes/Test/'  # Path to precomputed data
precompute = False  # Tells if the precomputed data is available
model_root = Path('/home/licho/Documentos/Stage/Article/training_models-main');  # Path to model saving files
expe_root = '/home/licho/Documentos/Stage/Codes/Test/expe_2/'  # # Path of experimental data
# -- Calculate the Noise Variance Matrix Stabilization (NVMS)
# -- In the experimental case (for testing only). We take the maximum intensity of the image , which is the size of the image.
NVMS = np.diag((img_size ** 2) * np.ones(CR))

#########################
# Optimisation parameters
#########################

# --network architecture --> ['c0mp', 'comp','pinv', 'free'] --> [0, 1, 2, 3]
net_type = ['NET_c0mp', 'NET_comp', 'NET_pinv', 'NET_free']
net_arch = 0  # Bayesian solution
num_epochs = 30  # Number of training epochs for simple schema
batch_size = 256  # Size of each training batch
reg = 1e-7  # Regularisation Parameter
lr = 1e-3  # Learning Rate
step_size = 10  # Scheduler Step Size
gamma = 0.5  # Scheduler Decrease Rate
Niter_simple = 1  # Number of net iterations for simple schema
Niter_comp = 5  # Number of net iterations for compound schema
eta = 2 # hyperparameter

# %% Loading Preprocessed Data
my_transform_file = Path(expe_root) / ('transform_{}x{}'.format(img_size, img_size) + '.mat')
H = sio.loadmat(my_transform_file);
H = (1 / img_size) * H["H"]

my_average_file = Path(precompute_root) / ('Average_{}x{}'.format(img_size, img_size) + '.npy')
my_cov_file = Path(precompute_root) / ('Cov_{}x{}'.format(img_size, img_size) + '.npy')
print('Loading covariance and mean')
Mean_had = np.load(my_average_file)
Cov_had = np.load(my_cov_file)
Mean_had = Mean_had / img_size  # Normalized mean vector
Cov_had = Cov_had / img_size ** 2  # Normalized covariance matrix
Ord = Cov2Var(Cov_had)  # Statistic order
Perm = Permutation_Matrix(Ord)

"""
my_average_file = Path(expe_root) / ('Average_{}x{}'.format(img_size, img_size) + '.mat')
my_cov_file = Path(expe_root) / ('Cov_{}x{}'.format(img_size, img_size) + '.mat')

print('Loading covariance and mean')
Mean_had_1 = sio.loadmat(my_average_file)
Cov_had_1 = sio.loadmat(my_cov_file)

# Normalisation of imported Mean and Covariance.
Mean_had_1 = Mean_had_1["mu"] - np.dot(H, np.ones((img_size ** 2, 1)));
Mean_had_1 = np.reshape(Mean_had_1, (img_size, img_size));
Mean_had_1 = np.amax(Mean_had) / np.amax(Mean_had_1) * Mean_had_1;
Cov_had_1 = Cov_had_1["C"];
Cov_had_1 = np.amax(Cov_had) / np.amax(Cov_had_1) * Cov_had_1;
Var = Cov2Var(Cov_had_1)
Perm = Permutation_Matrix(Var)
"""

########################
# -- Loading MMSE models
########################

###############################################################################
# model 1 : Denoising stage with full matrix inversion -- vanilla version (k=0)
###############################################################################

denoiCompNetFull = DenoiCompNet(img_size, CR, Mean_had, Cov_had, NVMS, Niter=Niter_simple, variant=net_arch, denoi=2, N0=N0, sig=sig, H=H)
denoiCompNetFull = denoiCompNetFull.to(device)

# -- Load net
suffix = '_N0_{}_sig_{}_Denoi_Full_Niter_{}_N_{}_M_{}_epo_{}_lr_{}_sss_{}_sdr_{}_bs_{}_reg_{}'.format(\
    N0, sig, Niter_simple, img_size, CR, num_epochs, lr, step_size, gamma, batch_size, reg)

title = model_root / (net_type[net_arch] + suffix)
load_net(title, denoiCompNetFull, device)

####################################################################
# model 2 : Denoising stage with diagonal matrix approximation (k=0)
####################################################################

denoiCompNet_simple = DenoiCompNet(img_size, CR, Mean_had, Cov_had, NVMS, Niter=Niter_simple, variant=net_arch, denoi=1, N0=N0, sig=sig, H=H)
denoiCompNet_simple = denoiCompNet_simple.to(device)

# -- Load net
suffix1 = '_N0_{}_sig_{}_Denoi_Diag_Niter_{}_N_{}_M_{}_epo_{}_lr_{}_sss_{}_sdr_{}_bs_{}_reg_{}'.format(\
    N0, sig, Niter_simple, img_size, CR, num_epochs, lr, step_size, gamma, batch_size, reg)

title1 = model_root / (net_type[net_arch] + suffix1)
load_net(title1, denoiCompNet_simple, device)

####################################################################
# model 3 : Denoising stage with diagonal matrix approximation (k=4)
####################################################################

denoiCompNet_iter = DenoiCompNet(img_size, CR, Mean_had, Cov_had, NVMS, Niter=Niter_comp, variant=net_arch, denoi=1, N0=N0, sig=sig, H=H)
denoiCompNet_iter = denoiCompNet_iter.to(device)

# -- Load net
suffix2 = '_N0_{}_sig_{}_Denoi_Diag_Niter_{}_N_{}_M_{}_epo_{}_lr_{}_sss_{}_sdr_{}_bs_{}_reg_{}'.format(\
    N0, sig, Niter_comp, img_size, CR, num_epochs, lr, step_size, gamma, batch_size, reg)

title2 = model_root / (net_type[net_arch] + suffix2)
load_net(title2, denoiCompNet_iter, device)

################################################################################
# model 4 : Denoising stage with a first order taylor approximation + NVMS (k=0)
################################################################################

denoiCompNetNVMS_simple = DenoiCompNet(img_size, CR, Mean_had, Cov_had, NVMS=NVMS, Niter=Niter_simple, variant=net_arch, denoi=0, N0=N0, sig=sig, H=H)
denoiCompNetNVMS_simple = denoiCompNetNVMS_simple.to(device)

# -- Load net
suffix3 = '_N0_{}_sig_{}_Denoi_NVMS_Max_Niter_{}_N_{}_M_{}_epo_{}_lr_{}_sss_{}_sdr_{}_bs_{}_reg_{}'.format(\
    N0, sig, Niter_simple, img_size, CR, num_epochs, lr, step_size, gamma, batch_size, reg)

title3 = model_root / (net_type[net_arch] + suffix3)
load_net(title3, denoiCompNetNVMS_simple, device)

################################################################################
# model 5 : Denoising stage with a first order taylor approximation + NVMS (k=4)
################################################################################

denoiCompNetNVMS_iter = DenoiCompNet(img_size, CR, Mean_had, Cov_had, NVMS=NVMS, Niter=Niter_comp, variant=net_arch, denoi=0, N0=N0, sig=sig, H=H)
denoiCompNetNVMS_iter = denoiCompNetNVMS_iter.to(device)

# -- Load net
suffix4 = '_N0_{}_sig_{}_Denoi_NVMS_Max_Niter_{}_N_{}_M_{}_epo_{}_lr_{}_sss_{}_sdr_{}_bs_{}_reg_{}'.format(\
    N0, sig, Niter_comp, img_size, CR, num_epochs, lr, step_size, gamma, batch_size, reg)

title4 = model_root / (net_type[net_arch] + suffix4)
load_net(title4, denoiCompNetNVMS_iter, device)

#####################
# -- Model evaluation
#####################

###################
# LED Lamp - Part 3
###################

#############################
# Loading the Compressed Data
#############################
#%% LED Lamp
# Loading compressed data

titles_expe = ["noObjectD_1_0.0_variance", "noObjectD_1_0.3_02_variance"] + \
              ["noObjectD_1_0.3_03_variance", "noObjectD_1_0.3_04_variance"] + \
              ["noObjectD_1_0.3_01_variance"] + \
              ["noObjectD_1_0.3_01_variance", "noObjectD_1_0.6_variance"] + \
              ["noObjectD_1_1.0_variance", "noObjectD_1_1.3_variance"]

channel = 548;

nflip = [1 for i in range(len(titles_expe))];
expe_data = [expe_root + titles_expe[i] for i in range(len(titles_expe))];

m_list = load_data_list_index(expe_data, nflip, CR, K, Perm, img_size, num_channel=channel);

m_prim = [];
m_prim.append(sum(m_list[:4]) + m_list[6]);
m_prim.append(sum(m_list[:2]));
m_prim.append(m_list[0]);
m_prim.append(m_list[6] + m_list[8]);
m_prim = m_prim + m_list[7:];
m_list = m_prim;

# Loading ground-truth
# NB: we normalize it to get the range the neural networks work with.
GT = raw_ground_truth_list_index(expe_data, nflip, H, img_size, num_channel=channel);

# Good values 450 - 530 -  548 - 600
GT_prim = [];
GT_prim.append(sum(GT[:4]) + GT[6]);
GT_prim.append(sum(GT[:2]));
GT_prim.append(GT[0]);
GT_prim.append(GT[6] + GT[8]);
GT_prim = GT_prim + GT[7:];
GT = GT_prim;

max_list = [np.amax(GT[i]) - np.amin(GT[i]) for i in range(len(GT))];
GT = [((GT[i] - np.amin(GT[i])) / max_list[i]) * 2 - 1 for i in range(len(GT))];
max_list = [max_list[i] / K for i in range(len(max_list))];

# %% Displaying the results
# Once all the networks have been loaded, we evaluate them on the measurements.

"""
titles = ["GT", "Diagonal approx (k=0)", "Taylor approx with NVMS (k=0)", "full Inverse (k=0)"]

title_lists = [];
Additional_info = [["N0 = {}".format(round(max_list[i])) if j == 0 else "" for j in range(len(titles))] for i in
                   range(len(max_list))]
Ground_truth = torch.Tensor(GT[0]).view(1, 1, 1, img_size, img_size).repeat(1, len(titles), 1, 1, 1);
outputs = [];

# noise_vec = [148, 80, 57, 25, 12, 9]

with torch.no_grad():
    for i in range(len(GT)):

        list_outs = [];
        m_list[i] = m_list[i] * eta;
        # temp = torch.ones([1, 1, 1024])

        x, var = denoiCompNet_simple.forward_variance(1 / K * m_list[i] , 1, 1, img_size, img_size)
        var = K * (var - 2 * C) + 2 * s ** 2
        x, N0_est = denoiCompNet_simple.forward_preprocess_expe(x, 1, 1, img_size, img_size)
        # N0_est = temp * noise_vec[i]
        print(N0_est)

        x_diag = denoiCompNet_simple.forward_denoise_expe(x, var, N0_est, 1, 1, img_size, img_size)
        f_diag = denoiCompNet_simple.forward_maptoimage(x_diag, 1, 1, img_size, img_size)
        # f_diag = denoiCompNet_simple.forward_postprocess(f_diag, 1, 1, img_size, img_size)

        NVMS_est = NVMS / N0_est[0, 0, 0].numpy()
        P0, P1, P2 = denoiCompNetNVMS_simple.forward_denoise_operators(Cov_had, NVMS_est, img_size, CR)
        x_nvms = denoiCompNetNVMS_simple.forward_denoise_expe_nvms(x, var, N0_est, P0, P1, P2, 1, 1, img_size, img_size)
        f_nvms = denoiCompNetNVMS_simple.forward_maptoimage(x_nvms, 1, 1, img_size, img_size)
        # f_nvms = denoiCompNetNVMS_simple.forward_postprocess(f_nvms, 1, 1, img_size, img_size)

        x_full = denoiCompNetFull.forward_denoise_expe(x, var, N0_est, 1, 1, img_size, img_size)
        f_full = denoiCompNetFull.forward_maptoimage(x_full, 1, 1, img_size, img_size)
        # f_full = denoiCompNetFull.forward_postprocess(f_full, 1, 1, img_size, img_size)

        gt = torch.Tensor(GT[i]).to(device);
        gt = gt.view(1, 1, img_size, img_size);
        list_outs.append(gt)
        list_outs.append(f_diag)
        list_outs.append(f_nvms)
        list_outs.append(f_full)
        output = torch.stack(list_outs, axis=1);

        psnr = batch_psnr_vid(Ground_truth, output);
        outputs.append(torch2numpy(output));
        title_lists.append(["{} {},\n PSNR = {}".format(titles[j], Additional_info[i][j], round(psnr[j], 2)) for j in
                            range(len(titles))]);

o1 = outputs;
t1 = title_lists;
nb_disp_frames = 4;
outputs_0 = outputs[:1];
outputs_1 = outputs[1:4];
outputs_2 = outputs[4:];
title_lists_0 = title_lists[:1];
title_lists_1 = title_lists[1:4];
title_lists_2 = title_lists[4:];

compare_video_frames(outputs_0, nb_disp_frames, title_lists_0);
compare_video_frames(outputs_1, nb_disp_frames, title_lists_1);
compare_video_frames(outputs_2, nb_disp_frames, title_lists_2);
"""

###################
# -- Net evaluation
###################
titles = ["GT", "Diagonal approx (k=0)", "Diagonal approx (k=5)", "NVMS (k=0)", "NVMS (k=5)", "full Inverse (k=0)"]

title_lists = [];
Additional_info = [["N0 = {}".format(round(max_list[i])) if j == 0 else "" for j in range(len(titles))] for i in
                   range(len(max_list))]
Ground_truth = torch.Tensor(GT[0]).view(1, 1, 1, img_size, img_size).repeat(1, len(titles), 1, 1, 1);
outputs = [];

with torch.no_grad():
    for i in range(len(GT)):

        list_outs = [];
        m_list[i] = m_list[i] * eta;

        f_net_diag = denoiCompNet_simple.forward_reconstruct_expe(1 / K * m_list[i], NVMS, 1, 1, img_size, img_size, C, s, K)
        f_net_diag_iter = denoiCompNet_iter.forward_reconstruct_expe(1 / K * m_list[i], NVMS, 1, 1, img_size, img_size, C, s, K)
        f_net_nvms = denoiCompNetNVMS_simple.forward_reconstruct_expe(1 / K * m_list[i], NVMS, 1, 1, img_size, img_size, C, s, K)
        f_net_nvms_iter = denoiCompNetNVMS_iter.forward_reconstruct_expe(1 / K * m_list[i], NVMS, 1, 1, img_size, img_size, C, s, K)
        f_net_full = denoiCompNetFull.forward_reconstruct_expe(1 / K * m_list[i], NVMS, 1, 1, img_size, img_size, C, s, K)

        gt = torch.Tensor(GT[i]).to(device);
        gt = gt.view(1, 1, img_size, img_size);
        list_outs.append(gt)
        list_outs.append(f_net_diag)
        list_outs.append(f_net_diag_iter)
        list_outs.append(f_net_nvms)
        list_outs.append(f_net_nvms_iter)
        list_outs.append(f_net_full)
        output = torch.stack(list_outs, axis=1);

        psnr = batch_psnr_vid(Ground_truth, output);
        outputs.append(torch2numpy(output));
        title_lists.append(["{} {},\n PSNR = {}".format(titles[j], Additional_info[i][j], round(psnr[j], 2)) for j in
                            range(len(titles))]);

o1 = outputs;
t1 = title_lists;
nb_disp_frames = 6;
outputs_0 = outputs[:1];
outputs_1 = outputs[1:4];
outputs_2 = outputs[4:];
title_lists_0 = title_lists[:1];
title_lists_1 = title_lists[1:4];
# title_lists_2 = title_lists[4:];

compare_video_frames(outputs_0, nb_disp_frames, title_lists_0);
compare_video_frames(outputs_1, nb_disp_frames, title_lists_1);
# compare_video_frames(outputs_2, nb_disp_frames, title_lists_2);

############
# STL-10 Cat
############

# Loading the Compressed Data
titles_expe = ["stl10_05_1.5_0.0_0{}_variance".format(i) for i in range(1, 7)] + \
              ["stl10_05_1_0.3_variance", "stl10_05_1_0.6_variance"]

expe_data = [expe_root + titles_expe[i] for i in range(len(titles_expe))];
nflip = [1.5 for i in range(len(titles_expe))];
nflip[-2:] = [1 for i in range(len(nflip[-2:]))]
channel = 581;
m_list = load_data_list_index(expe_data, nflip, CR, K, Perm, img_size, num_channel=channel);

m_prim = [];
m_prim.append(sum(m_list[:7]));
m_prim.append(m_list[0] + m_list[1]);
m_prim.append(m_list[2]);
m_prim = m_prim + m_list[-2:];
m_list = m_prim;

# Loading Ground-Truth
# NB: we normalize it to get the range the neural networks work with.

GT = raw_ground_truth_list_index(expe_data, nflip, H, img_size, num_channel=channel);
# Good values 450 - 530 -  548 - 600
GT_prim = [];
GT_prim.append(sum(GT[:7]));
GT_prim.append(GT[0] + GT[1]);
GT_prim.append(GT[2]);
GT_prim = GT_prim + GT[-2:];
GT = GT_prim;
max_list = [np.amax(GT[i]) - np.amin(GT[i]) for i in range(len(GT))];
GT = [((GT[i] - np.amin(GT[i])) / max_list[i]) * 2 - 1 for i in range(len(GT))];
max_list = [max_list[i] / K for i in range(len(max_list))];

"""
titles = ["GT", "Diagonal approx (k=0)", "Taylor approx with NVMS (k=0)", "full Inverse (k=0)"]

title_lists = [];
Additional_info = [["N0 = {}".format(round(max_list[i])) if j == 0 else "" for j in range(len(titles))] for i in
                   range(len(max_list))]
Ground_truth = torch.Tensor(GT[0]).view(1, 1, 1, img_size, img_size).repeat(1, len(titles), 1, 1, 1);
outputs = [];

# noise_vec = [195, 74, 44, 18, 10]

with torch.no_grad():
    for i in range(len(GT)):

        list_outs = [];
        m_list[i] = m_list[i] * eta;
        # temp = torch.ones([1, 1, 1024])

        x, var = denoiCompNet_simple.forward_variance(1 / K * m_list[i] , 1, 1, img_size, img_size)
        var = K * (var - 2 * C) + 2 * s ** 2
        x, N0_est = denoiCompNet_simple.forward_preprocess_expe(x, 1, 1, img_size, img_size)
        # N0_est = temp * noise_vec[i]
        print(N0_est)

        x_diag = denoiCompNet_simple.forward_denoise_expe(x, var, N0_est, 1, 1, img_size, img_size)
        f_diag = denoiCompNet_simple.forward_maptoimage(x_diag, 1, 1, img_size, img_size)

        NVMS_est = NVMS / N0_est[0, 0, 0].numpy()
        P0, P1, P2 = denoiCompNetNVMS_simple.forward_denoise_operators(Cov_had, NVMS_est, img_size, CR)
        x_nvms = denoiCompNetNVMS_simple.forward_denoise_expe_nvms(x, var, N0_est, P0, P1, P2, 1, 1, img_size, img_size)
        f_nvms = denoiCompNetNVMS_simple.forward_maptoimage(x_nvms, 1, 1, img_size, img_size)

        x_full = denoiCompNetFull.forward_denoise_expe(x, var, N0_est, 1, 1, img_size, img_size)
        f_full = denoiCompNetFull.forward_maptoimage(x_full, 1, 1, img_size, img_size)

        gt = torch.Tensor(GT[i]).to(device);
        gt = gt.view(1, 1, img_size, img_size);
        list_outs.append(gt)
        list_outs.append(f_diag)
        list_outs.append(f_nvms)
        list_outs.append(f_full)
        output = torch.stack(list_outs, axis=1);

        psnr = batch_psnr_vid(Ground_truth, output);
        outputs.append(torch2numpy(output));
        title_lists.append(["{} {},\n PSNR = {}".format(titles[j], Additional_info[i][j], round(psnr[j], 2)) for j in
                            range(len(titles))]);

o1 = outputs;
t1 = title_lists;
nb_disp_frames = 4;
outputs_0 = outputs[:1];
outputs_1 = outputs[1:4];
outputs_2 = outputs[4:];
title_lists_0 = title_lists[:1];
title_lists_1 = title_lists[1:4];
title_lists_2 = title_lists[4:];

compare_video_frames(outputs_0, nb_disp_frames, title_lists_0);
compare_video_frames(outputs_1, nb_disp_frames, title_lists_1);
compare_video_frames(outputs_2, nb_disp_frames, title_lists_2);
"""

###################
# -- Net evaluation
###################
titles = ["GT", "Diagonal approx (k=0)", "Diagonal approx (k=5)", "NVMS (k=0)", "NVMS (k=5)", "full Inverse (k=0)"]

title_lists = [];
Additional_info = [["N0 = {}".format(round(max_list[i])) if j == 0 else "" for j in range(len(titles))] for i in
                   range(len(max_list))]
Ground_truth = torch.Tensor(GT[0]).view(1, 1, 1, img_size, img_size).repeat(1, len(titles), 1, 1, 1);
outputs = [];

with torch.no_grad():
    for i in range(len(GT)):

        list_outs = [];
        m_list[i] = m_list[i] * eta;

        f_net_diag = denoiCompNet_simple.forward_reconstruct_expe(1 / K * m_list[i], NVMS, 1, 1, img_size, img_size, C, s, K)
        f_net_diag_iter = denoiCompNet_iter.forward_reconstruct_expe(1 / K * m_list[i], NVMS, 1, 1, img_size, img_size, C, s, K)
        f_net_nvms = denoiCompNetNVMS_simple.forward_reconstruct_expe(1 / K * m_list[i], NVMS, 1, 1, img_size, img_size, C, s, K)
        f_net_nvms_iter = denoiCompNetNVMS_iter.forward_reconstruct_expe(1 / K * m_list[i], NVMS, 1, 1, img_size, img_size, C, s, K)
        f_net_full = denoiCompNetFull.forward_reconstruct_expe(1 / K * m_list[i], NVMS, 1, 1, img_size, img_size, C, s, K)

        gt = torch.Tensor(GT[i]).to(device);
        gt = gt.view(1, 1, img_size, img_size);
        list_outs.append(gt)
        list_outs.append(f_net_diag)
        list_outs.append(f_net_diag_iter)
        list_outs.append(f_net_nvms)
        list_outs.append(f_net_nvms_iter)
        list_outs.append(f_net_full)
        output = torch.stack(list_outs, axis=1);

        psnr = batch_psnr_vid(Ground_truth, output);
        outputs.append(torch2numpy(output));
        title_lists.append(["{} {},\n PSNR = {}".format(titles[j], Additional_info[i][j], round(psnr[j], 2)) for j in
                            range(len(titles))]);

o2 = outputs;
t2 = title_lists;
nb_disp_frames = 6;
outputs_0 = outputs[:1];
outputs_1 = outputs[1:4];
outputs_2 = outputs[4:];
title_lists_0 = title_lists[:1];
title_lists_1 = title_lists[1:4];
# title_lists_2 = title_lists[4:];

compare_video_frames(outputs_0, nb_disp_frames, title_lists_0);
compare_video_frames(outputs_1, nb_disp_frames, title_lists_1);
# compare_video_frames(outputs_2, nb_disp_frames, title_lists_2);


###################
# %% Siemens Star #
###################

# Loading the compressed raw measurements
titles_expe = ["starSectorD_2_0.0_01_variance", "starSectorD_2_0.0_02_variance"] + \
              ["starSectorD_2_0.0_03_variance", "starSectorD_2_0.0_04_variance"] + \
              ["starSectorD_2_0.0_05_variance", "starSectorD_2_0.0_06_variance"] + \
              ["starSectorD_2_0.0_07_variance", "starSectorD_2_0.0_08_variance"] + \
              ["starSectorD_2_0.0_09_variance", "starSectorD_2_0.0_variance"] + \
              ["starSectorD_2_0.3_variance", "starSectorD_2_0.6_variance"] + \
              ["starSectorD_2_1.0_variance", "starSectorD_2_1.3_variance"]

channel = 510;

nflip = [2 for i in range(len(titles_expe))];
expe_data = [expe_root + titles_expe[i] for i in range(len(titles_expe))];

m_list = load_data_list_index(expe_data, nflip, CR, K, Perm, img_size, num_channel=channel);

m_prim = [];
m_prim.append(sum(m_list[:10]));
m_prim.append(m_list[10]);
m_list = m_prim;

# Loading Ground Truth
# NB: we normalize it to get the range the neural networks work with.
GT = raw_ground_truth_list_index(expe_data, nflip, H, img_size, num_channel=channel);
# Good values 450 - 530 -  548 - 600 -510

GT_prim = [];
GT_prim.append(sum(GT[:10]));
GT_prim.append(GT[10]);
GT = GT_prim;
max_list = [np.amax(GT[i]) - np.amin(GT[i]) for i in range(len(GT))];
#    GT = [((GT[i]-np.amin(GT[i]))/max_list[i]+1)/2 for i in range(len(GT))];
GT = [((GT[i] - np.amin(GT[i])) / max_list[i]) * 2 - 1 for i in range(len(GT))];
max_list = [max_list[i] / K for i in range(len(max_list))];

"""
titles = ["GT", "Diagonal approx (k=0)", "Taylor approx with NVMS (k=0)", "full Inverse (k=0)"]

# %% Methods comparison
m_list[0].shape

title_lists = [];
Additional_info = [["N0 = {}".format(round(max_list[i])) if j == 0 else "" for j in range(len(titles))] for i in
                   range(len(max_list))]
Ground_truth = torch.Tensor(GT[0]).view(1, 1, 1, img_size, img_size).repeat(1, len(titles), 1, 1, 1);
outputs = [];

with torch.no_grad():
    for i in range(len(GT)):

        list_outs = [];
        m_list[i] = m_list[i] * eta;
        # temp = torch.ones([1, 1, 1024])

        x, var = denoiCompNet_simple.forward_variance(1 / K * m_list[i] , 1, 1, img_size, img_size)
        var = K * (var - 2 * C) + 2 * s ** 2
        x, N0_est = denoiCompNet_simple.forward_preprocess_expe(x, 1, 1, img_size, img_size)
        # N0_est = temp * noise_vec[i]
        print(N0_est)

        x_diag = denoiCompNet_simple.forward_denoise_expe(x, var, N0_est, 1, 1, img_size, img_size)
        f_diag = denoiCompNet_simple.forward_maptoimage(x_diag, 1, 1, img_size, img_size)

        NVMS_est = NVMS / N0_est[0, 0, 0].numpy()
        P0, P1, P2 = denoiCompNetNVMS_simple.forward_denoise_operators(Cov_had, NVMS_est, img_size, CR)
        x_nvms = denoiCompNetNVMS_simple.forward_denoise_expe_nvms(x, var, N0_est, P0, P1, P2, 1, 1, img_size, img_size)
        f_nvms = denoiCompNetNVMS_simple.forward_maptoimage(x_nvms, 1, 1, img_size, img_size)

        x_full = denoiCompNetFull.forward_denoise_expe(x, var, N0_est, 1, 1, img_size, img_size)
        f_full = denoiCompNetFull.forward_maptoimage(x_full, 1, 1, img_size, img_size)

        gt = torch.Tensor(GT[i]).to(device);
        gt = gt.view(1, 1, img_size, img_size);
        list_outs.append(gt)
        list_outs.append(f_diag)
        list_outs.append(f_nvms)
        list_outs.append(f_full)
        output = torch.stack(list_outs, axis=1);

        psnr = batch_psnr_vid(Ground_truth, output);
        outputs.append(torch2numpy(output));
        title_lists.append(["{} {},\n PSNR = {}".format(titles[j], Additional_info[i][j], round(psnr[j], 2)) for j in
                            range(len(titles))]);

o3 = outputs
t3 = title_lists
nb_disp_frames = 4

outputs_0 = outputs[:1]
outputs_1 = outputs[1:4]
title_lists_0 = title_lists[:1]
title_lists_1 = title_lists[1:4]

compare_video_frames(outputs_0, nb_disp_frames, title_lists_0)
compare_video_frames(outputs_1, nb_disp_frames, title_lists_1)
"""

###################
# -- Net evaluation
###################
titles = ["GT", "Diagonal approx (k=0)", "Diagonal approx (k=5)", "NVMS (k=0)", "NVMS (k=5)", "full Inverse (k=0)"]

title_lists = [];
Additional_info = [["N0 = {}".format(round(max_list[i])) if j == 0 else "" for j in range(len(titles))] for i in
                   range(len(max_list))]
Ground_truth = torch.Tensor(GT[0]).view(1, 1, 1, img_size, img_size).repeat(1, len(titles), 1, 1, 1);
outputs = [];

with torch.no_grad():
    for i in range(len(GT)):

        list_outs = [];
        m_list[i] = m_list[i] * eta;

        f_net_diag = denoiCompNet_simple.forward_reconstruct_expe(1 / K * m_list[i], NVMS, 1, 1, img_size, img_size, C, s, K)
        f_net_diag_iter = denoiCompNet_iter.forward_reconstruct_expe(1 / K * m_list[i], NVMS, 1, 1, img_size, img_size, C, s, K)
        f_net_nvms = denoiCompNetNVMS_simple.forward_reconstruct_expe(1 / K * m_list[i], NVMS, 1, 1, img_size, img_size, C, s, K)
        f_net_nvms_iter = denoiCompNetNVMS_iter.forward_reconstruct_expe(1 / K * m_list[i], NVMS, 1, 1, img_size, img_size, C, s, K)
        f_net_full = denoiCompNetFull.forward_reconstruct_expe(1 / K * m_list[i], NVMS, 1, 1, img_size, img_size, C, s, K)

        gt = torch.Tensor(GT[i]).to(device);
        gt = gt.view(1, 1, img_size, img_size);
        list_outs.append(gt)
        list_outs.append(f_net_diag)
        list_outs.append(f_net_diag_iter)
        list_outs.append(f_net_nvms)
        list_outs.append(f_net_nvms_iter)
        list_outs.append(f_net_full)
        output = torch.stack(list_outs, axis=1);

        psnr = batch_psnr_vid(Ground_truth, output);
        outputs.append(torch2numpy(output));
        title_lists.append(["{} {},\n PSNR = {}".format(titles[j], Additional_info[i][j], round(psnr[j], 2)) for j in
                            range(len(titles))]);

o3 = outputs
t3 = title_lists
nb_disp_frames = 6

outputs_0 = outputs[:1]
outputs_1 = outputs[1:4]
title_lists_0 = title_lists[:1]
title_lists_1 = title_lists[1:4]

compare_video_frames(outputs_0, nb_disp_frames, title_lists_0)
compare_video_frames(outputs_1, nb_disp_frames, title_lists_1)

###################
# %% Final Figure #
###################
out_lamp = np.concatenate((np.reshape(o1[0][0, 0, 0, :, :], (1, 1, 1, img_size, img_size)), o1[-1]), axis=1)
title_lamp = [t1[0][0][:-11] + "(a)"] + t1[-1]

out_cat = np.concatenate((np.reshape(o2[0][0, 0, 0, :, :], (1, 1, 1, img_size, img_size)), o2[-1]), axis=1)
title_cat = [t2[0][0][:-11] + "(b)"] + t2[-1]

out_star = np.concatenate((np.reshape(o3[0][0, 0, 0, :, :], (1, 1, 1, img_size, img_size)), o3[-1]), axis=1)
title_star = [t3[0][0][:-11] + "(c)"] + t3[-1]

outputs = [out_lamp, out_cat, out_star]
title_lists = [title_lamp, title_cat, title_star]

nb_disp_frames = 7
compare_video_frames(outputs, nb_disp_frames, title_lists, 'eta = {}\n'.format(eta), fontsize=11.4)