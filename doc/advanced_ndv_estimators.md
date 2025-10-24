# Advanced NDV Estimators and Histogram Algorithms

## Table of Contents
- [Overview](#overview)
- [NDV Estimators](#ndv-estimators)
  - [PLM4NDV](#plm4ndv-pre-trained-language-model-for-ndv)
  - [AdaNDV](#adandv-adaptive-ndv-estimator)
  - [Traditional Statistical Methods](#traditional-statistical-methods)
- [Histogram Construction](#histogram-construction)
  - [2PHASE Algorithm](#2phase-algorithm)
- [Usage Examples](#usage-examples)
- [Performance Benchmarks](#performance-benchmarks)
- [Training Guidelines](#training-guidelines)
- [References](#references)

---

## Overview

This document describes advanced NDV (Number of Distinct Values) estimation methods and histogram construction algorithms integrated into VIDEX. These contributions enhance VIDEX's capability to provide accurate cardinality estimation for virtual indexes through:

- **PLM4NDV**: Deep learning-based NDV estimator using pre-trained language models
- **AdaNDV**: Adaptive neural network that combines multiple traditional statistical estimators
- **2PHASE Histogram**: Cross-validation based histogram construction with adaptive sampling
- **14 Traditional Statistical Estimators**: Comprehensive collection of proven statistical methods

These methods enable VIDEX to obtain high-quality statistics with minimal data access, avoiding expensive full table scans.

---

## NDV Estimators

### PLM4NDV (Pre-trained Language Model for NDV)

#### Algorithm Introduction

PLM4NDV (Minimizing Data Access for Number of Distinct Values Estimation with Pre-trained Language Models) is a novel approach that minimizes data access costs while maintaining estimation accuracy. It achieves this by leveraging:

1. **Semantic Information**: Column metadata (name, type, constraints) encoded via pre-trained language models (e.g., Sentence-T5)
2. **Multi-column Awareness**: Multi-head self-attention to capture inter-column relationships
3. **Optional Sample Statistics**: Frequency profiles from limited sequential access (e.g., first 100 rows)

**Key Innovation**: PLM4NDV can estimate NDV with **zero data access** (using only schema metadata) or with minimal sequential access, avoiding expensive random sampling.

<!-- **Model Architecture**:
```
Input: Column Embedding (768D) + log(N) + [Optional: Profile (100D)]
  ↓
Multi-Head Self-Attention (table-level context)
  ↓
MLP: 768+1[+100] → 384 → 128 → 64 → 1
  ↓
Output: log(D) → exp(·) = Estimated NDV
``` -->

#### Usage

```python
from sub_platforms.sql_opt.histogram.ndv_estimator import NDVEstimator

profile = estimator.build_column_profile(col_data)
ndv = estimator.estimator(
    r=len(col_data),
    profile=profile,
    method='PLM4NDV',
    column_name='',
    all_columns=[]
)

```

#### Model Files

- **Pre-trained Model**: `src/sub_platforms/sql_opt/histogram/resources/plm4ndv.pth`
- **Sentence Transformer**: `resources/sentence-transformers/sentence-t5-large/` (auto-downloaded if missing)

#### Performance Characteristics

| Access Mode | Median q-error | 90th %ile | 95th %ile |
|-------------|----------------|-----------|-----------|
| Sequential (100 rows) | 13.47 | 13.47 | 33.54 |
| Random (100 rows) | 2.14 | 3.07 | 4.69 |

**Best for**: Categorical columns, semantic-rich data, multi-column scenarios

---

### AdaNDV (Adaptive NDV Estimator)

#### Algorithm Introduction

AdaNDV addresses the long-standing challenge in NDV estimation: **no single estimator performs best across all scenarios**. It uses a learning-based approach to:

1. **Complementary Selection**: Separate rankers for over-estimators and under-estimators
2. **Adaptive Fusion**: Learned weighting of top-k estimators from each category
3. **Profile-driven**: Uses frequency profile to determine optimal estimator combination

**Key Innovation**: Instead of directly estimating NDV, AdaNDV learns to **select and fuse** existing statistical estimators based on data characteristics.
<!-- 
**Model Architecture**:
```
Input: Profile (97D) + [log(n), log(d), log(N)]
  ↓
Ranker_over:  100+3 → 128 → 64 → 9 (scores)
Ranker_under: 100+3 → 128 → 64 → 9 (scores)
  ↓
Select top-k=2 from each ranker → 4 estimators
  ↓
Weighter: 100+3+4 → 64 → 64 → 4 (softmax weights)
  ↓
Output: Weighted sum of log-estimates → exp(·) = Estimated NDV
``` -->

**Base Estimators** (9 total):
Error Bound, GEE, Chao, Shlosser, ChaoLee, Jackknife, Sichel, Method of Moments, Bootstrap

#### Usage

```python
from sub_platforms.sql_opt.histogram.ndv_estimator import NDVEstimator


# AdaNDV estimation
ndv = estimator.estimator(r=len(col_data), profile=profile, method='Ada')
```

#### Model Files

- **Pre-trained Model**: `src/sub_platforms/sql_opt/histogram/resources/adandv.pth`

#### Performance Characteristics

| Metric | AdaNDV | Best Single Estimator |
|--------|--------|----------------------|
| Mean q-error | 181 | ~250-300 |
| Robustness | High (combines multiple methods) | Varies by distribution |

**Best for**: Diverse data distributions, robust estimation across workloads

---

### Traditional Statistical Methods

VIDEX includes **14 traditional statistical NDV estimators** from database and statistics literature. These serve as:
- Baselines for comparison
- Base estimators for AdaNDV
- Fallback methods when ML models unavailable

#### Available Methods

| Method | Usage String | Reference | Characteristics |
|--------|-------------|-----------|----------------|
| **Scale** | `'scale'` | Simple ratio | Fast, assumes uniform sampling |
| **Error Bound** | `'error_bound'` | Custom | Conservative upper bound |
| **GEE** | `'GEE'` | Haas et al. 1995 | Good-Turing enhanced |
| **Chao** | `'Chao'` | Chao 1984 | Uses f1²/f2, good for long-tail |
| **Shlosser** | `'shlosser'` | Shlosser 1981 | Bernoulli sampling based |
| **ChaoLee** | `'ChaoLee'` | Chao & Lee 1992 | Coverage estimation |
| **Jackknife** | `'Jackknife'` | Burnham & Overton 1978 | Bias correction |
| **Sichel** | `'Sichel'` | Sichel 1986 | GIG-Poisson model |
| **Goodman** | `'Goodman'` | Goodman 1949 | Classical approach |
| **Method of Moments** | `'Method of Movement'` | Haas et al. 1995 | Exponential model |
| **Method of Moments v2** | `'Method of Movement v2'` | Haas et al. 1995 | Finite population |
| **Method of Moments v3** | `'Method of Movement v3'` | Haas et al. 1995 | Non-uniform frequency |
| **Bootstrap** | `'Bootstrap'` | Smith & Van Belle 1984 | Resampling-based |
| **Horvitz-Thompson** | `'Horvitz Thompson'` | Särndal et al. 1992 | Survey sampling |
| **Smoothed Jackknife** | `'Smoothed Jackknife'` | Haas et al. 1995 | Advanced bias correction |

#### Usage Example

```python
# Compare multiple methods
methods = ['scale', 'GEE', 'Chao', 'Jackknife', 'Ada', 'PLM4NDV']
for method in methods:
    ndv = estimator.estimator(r=sample_size, profile=profile, method=method)
    print(f"{method}: {ndv:.2f}")
```

---

## Histogram Construction

### 2PHASE Algorithm

#### Algorithm Introduction

The 2PHASE algorithm (from Chaudhuri et al. 2004) addresses histogram construction efficiency through **adaptive block-level sampling**. Traditional approaches either:
- Use full table scans (expensive)
- Use fixed-size samples (may over/under-sample)

**2PHASE Innovation**: Adaptively determines the minimal sample size needed to achieve target accuracy via cross-validation.

**Algorithm Flow**:
```
Phase 1: Determine Required Sample Size
  1. Initial sampling (e.g., 1000 rows via block-level access)
  2. Recursive cross-validation (sort & validate)
     - Split samples recursively
     - Build histogram on left, validate on right (and vice versa)
     - Record CV errors at multiple sample sizes
  3. Fit error curve: Error(r) = c/r
  4. Compute required size: r_required = c / (target_error²)

Phase 2: Build Final Histogram
  1. Sample additional rows if needed (total = r_required)
  2. Merge sorted samples
  3. Build equi-depth histogram
```

**Block-Level Sampling**: Uses primary key ranges for efficient sampling, avoiding `ORDER BY` on target column.


#### Integration with VIDEX

2PHASE is integrated into VIDEX's metadata collection pipeline:

```bash
# Use 2PHASE histogram construction
python src/sub_platforms/sql_opt/videx/scripts/videx_build_env.py \
    --target "your_target_connection" \
    --videx "your_videx_connection" \
    --hist_algo block_2phase
```

#### Performance Benchmarks

**TPC-H SF1 Results** (lineitem table):

| Column | ANALYZE Buckets | 2PHASE Buckets | Sample Rate | KL Divergence | Speedup |
|--------|----------------|----------------|-------------|---------------|---------|
| L_SUPPKEY | 16 | 16 | 10% | 1.69e-05 | 5.1x |
| L_QUANTITY | 16 | 16 | 10% | 0.02 | 1.21x |
| L_RETURNFLAG | 16 | 16 | 10% | 1.36e-11 | 2.65x |
| L_ORDERKEY | 16 | 16 | 10% | 4.7e-5 | 5.6x |

**Key Finding**: 2PHASE achieves comparable histogram quality with ~90% less sampling on large tables.

---

<!-- 
### Testing

```bash
# Test NDV estimators
cd src/sub_platforms/sql_opt/histogram
python test_estimators.py
python test_adandv.py
python test_plm4ndv_inference.py

# Test 2PHASE histogram
python test_2phase_comparison.py
```

---

## Performance Benchmarks

### NDV Estimation Accuracy

**Test Setup**: TabLib dataset (20,000+ tables), 1% random sampling

| Method | Median q-error | 90th %ile | 95th %ile |
|--------|----------------|-----------|-----------|
| Scale (baseline) | 5.2 | 15.3 | 28.7 |
| GEE | 2.8 | 8.4 | 14.2 |
| Chao | 2.6 | 9.1 | 16.8 |
| **AdaNDV** | **~1.9** | **~5.2** | **~9.8** |
| **PLM4NDV (random)** | **1.36** | **3.07** | **4.69** |
| **PLM4NDV (sequential)** | **2.06** | **13.47** | **33.54** |

### Histogram Construction Efficiency

**2PHASE vs Traditional (Full Scan)**:

| Table Size | Traditional Sample | 2PHASE Sample | Reduction | Time Saved |
|------------|-------------------|---------------|-----------|------------|
| 1M rows | 1,000,000 (100%) | ~12,000 (1.2%) | 98.8% | 156s |
| 10M rows | 10,000,000 (100%) | ~28,000 (0.28%) | 99.7% | 1,245s |

--- -->

## Training Guidelines

### PLM4NDV Training

**Note**: PLM4NDV training is performed in a separate repository. For detailed training instructions, please refer to:
- **Repository**: [PLM4NDV Training Code](https://github.com/bytedance/plm4ndv/)
- **Paper**: [SIGMOD 2025 PLM4NDV: Minimizing Data Access for Number of Distinct Values Estimation with Pre-trained Language Models](https://arxiv.org/abs/2504.00608)

**Quick Overview**:
1. Prepare your dataset (e.g., TabLib)
2. Generate semantic embeddings using Sentence-T5
3. Train model with attention mechanism
4. Export to `plm4ndv.pth`

**Deployment to VIDEX**:
```bash
# Copy trained model
cp /path/to/plm4ndv/ckpt/plm4ndv.pth \
   videx/src/sub_platforms/sql_opt/histogram/resources/

# Ensure sentence transformer is available (auto-downloaded on first use)
```

---

### AdaNDV Training

**Note**: AdaNDV training is performed in a separate repository. For detailed training instructions, please refer to:
- **Repository**: [AdaNDV Training Code](https://github.com/bytedance/adandv)
- **Paper**: [AdaNDV: Adaptive Number of Distinct Value Estimation via Learning to Select and Fuse Estimators](https://www.arxiv.org/pdf/2502.16190)

**Quick Overview**:
1. Implement 14 base statistical estimators (see [pydistinct](https://github.com/chanedwin/pydistinct))
2. Sample and preprocess dataset(e.g., TabLib)
3. Train ranker and weighter models
4. Export to `adandv.pth`

**Deployment to VIDEX**:
```bash
# Copy trained model
cp /path/to/adandv/ckpt/adandv.pth \
   videx/src/sub_platforms/sql_opt/histogram/resources/
```

---

## Integration with VIDEX

### Automatic Integration

The advanced NDV estimators are automatically available when model files are present:

```bash
# Check model files
ls src/sub_platforms/sql_opt/histogram/resources/
# Expected: plm4ndv.pth, adandv.pth, sentence-transformers/
```

### Using with videx_build_env.py

```bash
# Build VIDEX environment with sampling
python src/sub_platforms/sql_opt/videx/scripts/videx_build_env.py \
    --target "your_target_connection" \
    --videx "your_videx_connection" \
    --fetch_method sampling \
    --hist_algo block_2phase

# Advanced NDV estimators (PLM4NDV/AdaNDV) are used automatically
# 2PHASE histogram is used when --hist_algo block_2phase is specified
```

### Programmatic Usage

```python
from sub_platforms.sql_opt.histogram.ndv_estimator import NDVEstimator

# Initialize (models loaded lazily on first use)
estimator = NDVEstimator(original_num=table_rows)

# Use specific method
ndv = estimator.estimator(
    r=sample_size,
    profile=profile,
    method='PLM4NDV'  # or 'Ada', 'GEE', etc.
)
```

---

## References

### Papers

1. **VIDEX System**:
   - Kang et al. "VIDEX: A Disaggregated and Extensible Virtual Index for the Cloud and AI Era" VLDB 2025
   - arXiv: https://arxiv.org/pdf/2503.23776

2. **PLM4NDV**:
   - Xu et al. "PLM4NDV: Minimizing Data Access for Number of Distinct Values Estimation with Pre-trained Language Models" SIGMOD 2025
   - arXiv: https://arxiv.org/abs/2504.00608

3. **AdaNDV**:
   - Xu et al. "AdaNDV: Adaptive Number of Distinct Value Estimation via Learning to Select and Fuse Estimators" VLDB 2025
   - arXiv: https://www.arxiv.org/abs/2502.16190

4. **2PHASE Histogram**:
   - Chaudhuri et al. "Effective use of block-level sampling in statistics estimation" SIGMOD 2004
   - https://dl.acm.org/doi/10.1145/1007568.1007602


### Code References

- **Implementation Files**:
  - `src/sub_platforms/sql_opt/histogram/ndv_estimator.py`
  - `src/sub_platforms/sql_opt/histogram/plm4ndv_model_infer.py`
  - `src/sub_platforms/sql_opt/histogram/adandv_model_infer.py`
  - `src/sub_platforms/sql_opt/histogram/histogram_utils.py`


### Contact

For questions or contributions:
- Open an issue on the VIDEX GitHub repository
- Contact: See AUTHORS file for contributor information


