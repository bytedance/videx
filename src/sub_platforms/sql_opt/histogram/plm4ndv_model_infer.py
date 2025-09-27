# -*- coding: utf-8 -*-
"""
Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
SPDX-License-Identifier: MIT
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from sentence_transformers import SentenceTransformer
from typing import List, Dict, Any
import os


class MultiHeadSelfAttention(nn.Module):
    def __init__(self, embed_dim, num_heads=8):
        super(MultiHeadSelfAttention, self).__init__()
        self.embed_dim = embed_dim
        self.num_heads = num_heads
        self.head_dim = embed_dim // num_heads
        
        assert (
            self.head_dim * num_heads == embed_dim
        ), "Embedding dimension must be divisible by number of heads"

        self.query = nn.Linear(embed_dim, embed_dim)
        self.key = nn.Linear(embed_dim, embed_dim)
        self.value = nn.Linear(embed_dim, embed_dim)
        self.fc_out = nn.Linear(embed_dim, embed_dim)
        self.dropout = nn.Dropout(0.5) 

    def forward(self, embedding_pad, mask):
        batch_size, seq_len, _ = embedding_pad.size()
        Q = self.query(embedding_pad) 
        K = self.key(embedding_pad)     
        V = self.value(embedding_pad)  

        Q = Q.view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2) 
        K = K.view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        V = V.view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)

        # 计算注意力得分
        attn_scores = torch.matmul(Q, K.transpose(-2, -1)) / (self.head_dim ** 0.5) 
        mask = mask.unsqueeze(1).unsqueeze(2) 
        mask = mask.expand(-1, self.num_heads, -1, -1)  
        mask = mask.expand(-1, -1, seq_len, -1)  

        if mask is not None:
            attn_scores.masked_fill_(mask == 0, float('-inf'))

        attn_weights = F.softmax(attn_scores, dim=-1)
        attn_weights = self.dropout(attn_weights) 

        output = torch.matmul(attn_weights, V) 

        output = output.transpose(1, 2).contiguous().view(batch_size, seq_len, self.embed_dim)

        output = self.fc_out(output) 
        output = self.dropout(output)  
        
        return output, attn_weights

class PLM4NDVModel(nn.Module):
    def __init__(self, input_len=768, profile_len=100, num_layers=1, use_sample=True):
        super(PLM4NDVModel, self).__init__()
        # table representation
        self.attentions = nn.ModuleList()
        for i in range(num_layers):
            self.attentions.append(MultiHeadSelfAttention(input_len))
        
        # 根据是否使用sample数据决定输入维度
        if use_sample:
            estimate_input_len = input_len + 1 + profile_len
        else:
            estimate_input_len = input_len + 1
            
        # NDV estimation
        self.sentence_transform = nn.Sequential(
            nn.Linear(estimate_input_len, 384),
            nn.ReLU(),
            nn.Linear(384, 128),
            nn.ReLU(),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )
        self.use_sample = use_sample
    
    def run(self, emb, N, profile, mask):
        x = emb
        for attention in self.attentions:
            x, attn_weights = attention(x, mask) 
        emb_transformed = x
        
        if self.use_sample:
            x = torch.concat((emb + emb_transformed, torch.log(N), profile[:,:,1:]), dim=-1) # [batch, seq_len, estimate_input_len]
        else:
            x = torch.concat((emb + emb_transformed, torch.log(N)), dim=-1) # [batch, seq_len, without sample]
        ans = self.sentence_transform(x)
        return ans.squeeze()
        
    def inference(self, emb, N, profile, mask):
        ans = self.run(emb, N, profile, mask)
        estimate_d = torch.exp(ans)
        return estimate_d.squeeze()
    
    def forward(self, emb, N, profile, mask):
        ans = self.run(emb, N, profile, mask)
        return ans

class PLM4NDVPredictor:
    def __init__(self, model_path: str = None, device: str = "cpu", use_sample: bool = True):
        """
        初始化PLM4NDV预测器
        
        Args:
            model_path: 模型权重文件路径
            device: 计算设备
            use_sample: 是否使用sample数据（对应原始代码中的args.sample）
        """
        # self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.device = torch.device("cpu")
        self.embedding_model = None
        self.plm_model = None
        self.use_sample = use_sample
        
        # 模型参数 - 与原始训练代码保持一致
        self.EMB_SIZE = 768
        self.PROFILE_SIZE = 100
        self.NUM_LAYERS = 1  # 对应原始代码中的args.layer，默认为1
        self.NUM_HEADS = 8   # 对应原始代码中的args.head，默认为8
        
        # 初始化模型
        self._init_models(model_path)
    
    def _init_models(self, model_path: str):
        """初始化embedding模型和PLM4NDV模型"""
        try:
            # 初始化sentence transformer模型 - 优先使用plm4ndv项目中的本地模型
            local_model_dir = "src/sub_platforms/sql_opt/histogram/resources/sentence-transformers/sentence-t5-large"
            if os.path.exists(local_model_dir):
                print(f"使用plm4ndv项目中的本地模型: {local_model_dir}")
                self.embedding_model = SentenceTransformer(local_model_dir)
            else:
                print("plm4ndv项目中的模型不存在，使用Hugging Face Hub模型...")
                self.embedding_model = SentenceTransformer('sentence-transformers/sentence-t5-large')
            
            self.embedding_model.to(self.device)
            
            # 初始化PLM4NDV模型 - 与原始训练代码保持一致
            self.plm_model = PLM4NDVModel(
                input_len=self.EMB_SIZE, 
                profile_len=self.PROFILE_SIZE,
                num_layers=self.NUM_LAYERS,
                use_sample=self.use_sample
            )
            
            # 加载预训练权重
            if model_path and os.path.exists(model_path):
                self.plm_model.load_state_dict(torch.load(model_path, map_location=self.device))
                print(f"PLM4NDV model loaded from {model_path}")
            else:
                print("Warning: No model weights loaded, using random initialization")
            
            self.plm_model.to(self.device)
            self.plm_model.eval()
            
        except Exception as e:
            print(f"Error initializing models: {e}")
            raise
    
    def generate_column_embedding(self, column_name: str, column_type: str, N: int, D: int) -> np.ndarray:
        """
        生成列的embedding，参考semantic_embedding.py的实现
        
        Args:
            column_name: 列名
            column_type: 列类型
            N: 表行数
            D: 该列的NDV
            
        Returns:
            embedding: 768维向量
        """
        # 构建列描述，与plm4ndv训练时完全一致
        # 格式: "列名, 类型, N, D" -> 去掉N,D -> "列名, 类型"
        col_description = f"{column_name}, {column_type}, {N}, {D}"
        # 去掉最后两个字段（N, D），与semantic_embedding.py第62行一致
        col_description = ','.join(col_description.split(',')[:-2])
        
        # 生成embedding
        with torch.no_grad():
            embedding = self.embedding_model.encode([col_description], device=self.device)
        
        return embedding[0]  # 返回第一个（也是唯一的）embedding
    
    def predict_table(self, columns_info: List[Dict[str, Any]], max_column_num: int = None) -> List[float]:
        """
        预测整个表格的NDV（多列估计，更接近原始训练设计）
        
        Args:
            columns_info: 列信息列表，每个字典包含：
                - profile: 频率分布
                - N: 总行数
                - D: 采样中的唯一值数量
                - column_name: 列名
                - column_type: 列类型
            max_column_num: 最大列数（用于填充，如果为None则使用实际列数）
                
        Returns:
            predicted_ndvs: 预测的NDV列表
        """
        try:
            if not columns_info:
                return []
            
            # 确定是否需要填充
            if max_column_num is None:
                max_column_num = len(columns_info)
            
            # 生成所有列的embedding
            embeddings = []
            N_list = []
            D_list = []
            profiles = []
            
            for col_info in columns_info:
                embedding = self.generate_column_embedding(
                    col_info['column_name'], 
                    col_info['column_type'],
                    col_info['N'],
                    col_info['D']
                )
                embeddings.append(embedding)
                N_list.append(col_info['N'])
                D_list.append(col_info['D'])
                
                # 处理profile
                profile = col_info['profile']
                if len(profile) < self.PROFILE_SIZE + 1:
                    profile_padded = profile + [0] * (self.PROFILE_SIZE + 1 - len(profile))
                else:
                    profile_padded = profile[:self.PROFILE_SIZE + 1]
                profiles.append(profile_padded)
            
            # 如果需要填充，添加占位列
            pad_len = max_column_num - len(columns_info)
            if pad_len > 0:
                # 添加填充的embedding
                zero_embedding = np.zeros(self.EMB_SIZE)
                embeddings.extend([zero_embedding] * pad_len)
                N_list.extend([1] * pad_len)
                D_list.extend([1] * pad_len)
                zero_profile = [0] * (self.PROFILE_SIZE + 1)
                profiles.extend([zero_profile] * pad_len)
            
            # 准备输入数据 - 使用固定长度，与训练时保持一致
            emb = torch.tensor(embeddings, dtype=torch.float32).unsqueeze(0)  # [1, max_column_num, 768]
            N_tensor = torch.tensor(N_list, dtype=torch.float32).unsqueeze(0)  # [1, max_column_num]
            profile_tensor = torch.tensor(profiles, dtype=torch.float32).unsqueeze(0)  # [1, max_column_num, 101]
            mask = torch.tensor([1] * len(columns_info) + [0] * pad_len, dtype=torch.float32).unsqueeze(0)  # [1, max_column_num]
            
            # 移动到设备
            emb = emb.to(self.device)
            N_tensor = N_tensor.to(self.device)
            profile_tensor = profile_tensor.to(self.device)
            mask = mask.to(self.device)
            
            # 推理
            with torch.no_grad():
                predicted_ndvs = self.plm_model.inference(emb, N_tensor.unsqueeze(-1), profile_tensor, mask)
            
            # 只返回真实列的预测结果
            # 处理不同维度的输出
            if predicted_ndvs.dim() == 0:
                # 0维张量：单列预测，返回单个值
                result = predicted_ndvs.cpu().numpy().tolist()
                return [result]
            elif predicted_ndvs.dim() == 1:
                # 1维张量：多列预测，返回前len(columns_info)个结果
                return predicted_ndvs[:len(columns_info)].cpu().numpy().tolist()
            else:
                # 2维张量：batch预测，返回第一行的前len(columns_info)个结果
                return predicted_ndvs[0][:len(columns_info)].cpu().numpy().tolist()
            
        except Exception as e:
            print(f"Error in PLM4NDV table prediction: {e}")
            # 返回fallback值
            return [col_info['D'] * 2 for col_info in columns_info]
    

