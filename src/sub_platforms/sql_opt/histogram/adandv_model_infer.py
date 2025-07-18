# adandv_model_infer.py
import os
import torch
import torch.nn as nn
import numpy as np


class AdaNDVConfig:
    def __init__(self,
                 model_path: str,
                 model_input_len: int = 100,
                 estimator_num: int = 14,
                 k: int = 2,
                 sample_rate: float = 0.01):
        self.model_path = model_path
        self.model_input_len = model_input_len
        self.estimator_num = estimator_num
        self.k = k
        self.sample_rate = sample_rate

class Ranker(nn.Module):
    def __init__(self, input_len, output_len):
        super().__init__()
        self.hidden_size = 128
        self.layers = nn.Sequential(
            nn.Linear(input_len, self.hidden_size),
            nn.ReLU(),
            nn.Linear(self.hidden_size, 64),
            nn.ReLU(), 
            nn.Linear(64, output_len)
        )
    def forward(self, x):
        return self.layers(x)

class Weighter(nn.Module):
    def __init__(self, input_len, output_len):
        super().__init__()
        self.hidden_size = 64
        self.layers = nn.Sequential(
            nn.Linear(input_len, self.hidden_size),
            nn.ReLU(),
            nn.Linear(self.hidden_size, 64),
            nn.ReLU(), 
            nn.Linear(64, output_len),
            nn.Softmax(dim=-1)
        )
    def forward(self, x):
        return self.layers(x)

class AdaNDV(nn.Module):
    def __init__(self, input_len=100, output_len=14, k=2):
        super().__init__()
        self.k = k
        self.ranker_over = Ranker(input_len, output_len)
        self.ranker_under = Ranker(input_len, output_len)
        self.weighter = Weighter(input_len + 2 * k, 2 * k)

    def forward(self, x, estimated_logd):
        return self.run(x, estimated_logd)

    def run(self, x, estimated_logd):
        score_over = self.ranker_over(x)
        _, over_idxs = torch.topk(score_over, self.k, dim=1)
        score_under = self.ranker_under(x)
        _, under_idxs = torch.topk(score_under, self.k, dim=1)

        over_estimate = estimated_logd[torch.arange(estimated_logd.shape[0]).unsqueeze(1), over_idxs]
        under_estimate = estimated_logd[torch.arange(estimated_logd.shape[0]).unsqueeze(1), under_idxs]
        estimate = torch.cat([over_estimate, under_estimate], dim=-1)

        x_prime = torch.cat([x, estimate], dim=-1)
        weights = self.weighter(x_prime)

        logd = torch.sum(estimate * weights, dim=-1).squeeze(-1)
        return score_over, score_under, logd

    def inference(self, x, estimated_logd):
        _, _, logd = self.run(x, estimated_logd)
        return logd

class AdaNDVPredictor:
    def __init__(self, config: AdaNDVConfig):
        self.config = config
        self.model = AdaNDV(
            input_len=config.model_input_len,
            output_len=config.estimator_num,
            k=config.k
        )
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.load_state_dict(torch.load(config.model_path, map_location=device))
        self.model.eval()

    def predict(self, profile, estimate_list):
        pad_len = self.config.model_input_len - 3  # 实验默认=97
        profile = profile[:pad_len] + [0] * (pad_len - len(profile))

        logn = np.log(np.dot(np.arange(len(profile)), profile))
        logd = np.log(np.sum(profile))
        logN = np.log(np.dot(np.arange(len(profile)), profile) / self.config.sample_rate)

        data_input = profile + [logn, logd, logN]
        x = torch.tensor([data_input], dtype=torch.float32)

        est_log = np.log(np.maximum(estimate_list, 1e-10))
        est_log = torch.tensor([est_log], dtype=torch.float32)

        logd_pred = self.model.inference(x, est_log)
        d_pred = torch.exp(logd_pred).item()
        return d_pred
