import logging

import numpy as np
import pandas as pd
from typing import List, Dict

import sqlglot.expressions

def mapping_index_columns(table):
    column_dict = {}
    for column in table.columns:
        column_dict[column.column_name] = column
    for index in table.indexes:
        for index_column in index.columns:
            #TODO paser expr mapping to cols
            continue
           