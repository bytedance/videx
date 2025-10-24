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

        # Calculate attention scores
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
        Initialize the PLM4NDV predictor
        
        Args:
            model_path: model weight file path
            device: compute device
            use_sample: whether to use sample data (corresponds to args.sample in the original code)
        """
        # self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.device = torch.device("cpu")
        self.embedding_model = None
        self.plm_model = None
        self.use_sample = use_sample
        
        # Model parameters - consistent with the original training code
        self.EMB_SIZE = 768
        self.PROFILE_SIZE = 100
        self.NUM_LAYERS = 1  # Corresponds to args.layer in the original code, default is 1
        self.NUM_HEADS = 8   # Corresponds to args.head in the original code, default is 8
        
        # Initialize models
        self._init_models(model_path)
    
    def _init_models(self, model_path: str):
        """Initialize the embedding model and PLM4NDV model"""
        try:
            # Initialize the sentence transformer model - use the local model in the plm4ndv project first
            local_model_dir = "src/sub_platforms/sql_opt/histogram/resources/sentence-transformers/sentence-t5-large"
            if os.path.exists(local_model_dir):
                print(f"Using the local model in the plm4ndv project: {local_model_dir}")
                self.embedding_model = SentenceTransformer(local_model_dir)
            else:
                print("The model in the plm4ndv project does not exist, using the Hugging Face Hub model...")
                self.embedding_model = SentenceTransformer('sentence-transformers/sentence-t5-large')
            
            self.embedding_model.to(self.device)
            
            # Initialize the PLM4NDV model - consistent with the original training code
            self.plm_model = PLM4NDVModel(
                input_len=self.EMB_SIZE, 
                profile_len=self.PROFILE_SIZE,
                num_layers=self.NUM_LAYERS,
                use_sample=self.use_sample
            )
            
            # Load the pre-trained weights
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
        Generate the column embedding, refer to the implementation of semantic_embedding.py
        
        Args:
            column_name: column name
            column_type: column type
            N: table rows
            D: NDV of this column
            
        Returns:
            embedding: a 768-dimensional vector
        """
        # Build the column description, consistent with the training of plm4ndv
        # Format: "column name, type, N, D" -> remove N,D -> "column name, type"
        col_description = f"{column_name}, {column_type}, {N}, {D}"
        # Remove the last two fields (N, D), consistent with the 62nd line of semantic_embedding.py
        col_description = ','.join(col_description.split(',')[:-2])
        
        # Generate the embedding
        with torch.no_grad():
            embedding = self.embedding_model.encode([col_description], device=self.device)
        
        return embedding[0]  # Return the first (and only) embedding
    
    def predict_table(self, columns_info: List[Dict[str, Any]], max_column_num: int = None) -> List[float]:
        """
        Predict the NDV of the entire table (multi-column estimation, closer to the original training design)
        
        Args:
            columns_info: list of column information, each dictionary contains:
                - profile: frequency distribution
                - N: total rows
                - D: unique values in the sampled data
                - column_name: column name
                - column_type: column type
            max_column_num: maximum number of columns (for padding, if None, use the actual number of columns)
                
        Returns:
            predicted_ndvs: list of predicted NDVs
        """
        try:
            if not columns_info:
                return []
            
            # Determine if padding is needed
            if max_column_num is None:
                max_column_num = len(columns_info)
            
            # Generate the embedding for all columns
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
                
                # Process the profile
                profile = col_info['profile']
                if len(profile) < self.PROFILE_SIZE + 1:
                    profile_padded = profile + [0] * (self.PROFILE_SIZE + 1 - len(profile))
                else:
                    profile_padded = profile[:self.PROFILE_SIZE + 1]
                profiles.append(profile_padded)
            
            # If padding is needed, add placeholder columns
            pad_len = max_column_num - len(columns_info)
            if pad_len > 0:
                # Add the embedding of the padded columns
                zero_embedding = np.zeros(self.EMB_SIZE)
                embeddings.extend([zero_embedding] * pad_len)
                N_list.extend([1] * pad_len)
                D_list.extend([1] * pad_len)
                zero_profile = [0] * (self.PROFILE_SIZE + 1)
                profiles.extend([zero_profile] * pad_len)
            
            # Prepare the input data - use fixed length, consistent with the training
            emb = torch.tensor(embeddings, dtype=torch.float32).unsqueeze(0)  # [1, max_column_num, 768]
            N_tensor = torch.tensor(N_list, dtype=torch.float32).unsqueeze(0)  # [1, max_column_num]
            profile_tensor = torch.tensor(profiles, dtype=torch.float32).unsqueeze(0)  # [1, max_column_num, 101]
            mask = torch.tensor([1] * len(columns_info) + [0] * pad_len, dtype=torch.float32).unsqueeze(0)  # [1, max_column_num]
            
            # Move to the device
            emb = emb.to(self.device)
            N_tensor = N_tensor.to(self.device)
            profile_tensor = profile_tensor.to(self.device)
            mask = mask.to(self.device)
            
            # Inference
            with torch.no_grad():
                predicted_ndvs = self.plm_model.inference(emb, N_tensor.unsqueeze(-1), profile_tensor, mask)
            
            # Only return the predicted results for the real columns
            # Process the output of different dimensions
            if predicted_ndvs.dim() == 0:
                # 0-dimensional tensor: single column prediction, return a single value
                result = predicted_ndvs.cpu().numpy().tolist()
                return [result]
            elif predicted_ndvs.dim() == 1:
                # 1-dimensional tensor: multiple column prediction, return the first len(columns_info) results
                return predicted_ndvs[:len(columns_info)].cpu().numpy().tolist()
            else:
                # 2-dimensional tensor: batch prediction, return the first len(columns_info) results of the first row
                return predicted_ndvs[0][:len(columns_info)].cpu().numpy().tolist()
            
        except Exception as e:
            print(f"Error in PLM4NDV table prediction: {e}")
            # Return the fallback value
            return [col_info['D'] * 2 for col_info in columns_info]
    

