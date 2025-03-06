# -*- coding: utf-8 -*-
"""
TODO: add file description.

@ author: kangrong
@ date: 2023/11/16
"""
import base64
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import List, Optional, Union, Dict

from dataclasses_json import dataclass_json

from sub_platforms.sql_opt.env.rds_env import Env
from sub_platforms.sql_opt.meta import Table, Column
from sub_platforms.sql_opt.videx.videx_utils import BTreeKeySide, target_env_available_for_videx, parse_datetime, \
    data_type_is_int, reformat_datetime_str

MEANINGLESS_INT = -1357


def decode_base64(raw):
    """
    'base64' 是表示数据编码方式的标识符，意味着后面的数据是用 Base64 方式编码的。
    'type254' 可能是表示数据类型的标识符。在 MySQL 中，数据类型的编号 254 通常代表 CHAR 类型，但具体含义可能取决于你的特定上下文。
    Args:
        raw:

    Returns:

    """

    decode_type, char_type, s = raw.split(":")
    assert decode_type == "base64" and char_type == "type254"
    base64_bytes = s.encode('utf-8')
    message_bytes = base64.b64decode(base64_bytes)
    return message_bytes.decode('utf-8')


def is_base64(str_in_base4: bool, raw):
    if not str_in_base4:
        return False
    if len(raw.split(":")) != 3:
        return False
    decode_type, char_type, s = raw.split(":")
    if decode_type == "base64" and char_type == "type254":
        return True
    return False


def convert_str_by_type(raw, data_type: str, str_in_base4: bool = True):
    """

    Args:
        raw:
        data_type:
        str_in_base4: if True，str is base64, need to decode

    Returns:

    """
    NULL_STR_SET = {'NULL', 'None'}
    if data_type_is_int(data_type):
        if raw in NULL_STR_SET:
            return None
        return int(float(raw))
    elif data_type in ['float', 'double']:
        if raw in NULL_STR_SET:
            return None
        return float(raw)
    elif data_type in ['string', 'str']:
        # "base64:type254:YXhhaGtyc2I="
        if is_base64(str_in_base4, raw):
            res = decode_base64(raw)
        else:
            res = str(raw)
        res = res.strip(' ')
        if (res.startswith("`") and res.endswith("`")) or \
                (res.startswith("'") and res.endswith("'")) or \
                (res.startswith('"') and res.endswith('"')):
            res = res[1:-1]
        return res
    elif data_type in ['datetime', 'date']:
        if '0000-00-00' in str(raw) or '1-01-01 00:00:00' in str(raw):
            return raw
        return reformat_datetime_str(str(raw))
    elif data_type == 'decimal':
        # we omit the point part in decimal
        return float(raw)
    elif data_type == 'json':
        # TODO: Temporarily handle JSON as a string for now. But in fact, we should parse the JSON and
        #  then perform function processing.
        return str(raw)
    else:
        # datetime,
        raise ValueError(f"Not support data type: {data_type}")


@dataclass_json
@dataclass
class HistogramBucket:
    min_value: Union[int, float, str, bytes]
    max_value: Union[int, float, str, bytes]
    # cumulative_frequency: float
    cum_freq: float
    row_count: float  # note，row_count is "ndv" in bucket，we use float since algorithm may return non-integer
    size: int = 0


def init_bucket_by_type(bucket_raw: list, data_type: str, hist_type: str) -> HistogramBucket:
    """
    init HistogramBucket

    Args:
        bucket_raw:
            {
                "min_value": "base64:type254:YXhhaGtyc2I=",
                "max_value": "base64:type254:ZHZ1bXV1eWVh",
                "cum_freq": 0.1,
                "row_count": 8
            },
        data_type: string, int, decimal, ...
        hist_type:

    Returns:

    """
    if hist_type == 'singleton':
        assert len(bucket_raw) == 2, f"Singleton bucket must have 2 elements, got {len(bucket_raw)}"

    if len(bucket_raw) == 2:
        min_value, max_value, cum_freq, row_count = bucket_raw[0], bucket_raw[0], bucket_raw[1], 1
    elif len(bucket_raw) == 4:
        min_value, max_value, cum_freq, row_count = bucket_raw
    else:
        raise NotImplementedError(f"Not support bucket with len!=2, 4 yet: {bucket_raw}")
    min_value, max_value = convert_str_by_type(min_value, data_type), convert_str_by_type(max_value, data_type)
    bucket = HistogramBucket(min_value=min_value, max_value=max_value, cum_freq=cum_freq, row_count=row_count)
    return bucket


@dataclass_json
@dataclass
class HistogramStats:
    """
    bucket.min_value <= bucket.max_value，
    且 buckets 是递增的，bucket[i].max_value <= bucket[i + 1].min_value
    但是 buckets 之间可能有间隔，例如 [1,2], [3,4]
    但这并不意味着间隔，而是说相邻但不重叠的边界。
    用 double 距离，bucket 之间：
    [
      6.22951651565178,
      8.72513181167602,
      0.1002,
      2004
    ],
    [
      8.72524160458256,
      9.18321476620723,
      0.2004,
      2004
    ],
    看起来相邻两个边界可以认为是不重叠、但也不遗漏的

    for int：
    {
    "min_value": 2401,
    "max_value": 2700,
    "cum_freq": 0.9,
    "row_count": 300
    },
    {
    "min_value": 2701,
    "max_value": 3000,
    "cum_freq": 1,
    "row_count": 300
    }
    """
    # table_rows: int
    buckets: Optional[List[HistogramBucket]]
    data_type: Optional[str]
    histogram_type: Optional[str]
    null_values: Optional[float] = MEANINGLESS_INT
    collation_id: Optional[int] = MEANINGLESS_INT
    last_updated: Optional[str] = str(MEANINGLESS_INT)
    sampling_rate: Optional[float] = MEANINGLESS_INT
    number_of_buckets_specified: Optional[int] = MEANINGLESS_INT

    def __post_init__(self):
        for b in self.buckets:
            b.min_value = convert_str_by_type(b.min_value, self.data_type)
            b.max_value = convert_str_by_type(b.max_value, self.data_type)

    def find_nearest_key_pos(self, value, side: BTreeKeySide) -> Union[int, float]:
        """
        TODO 从 HistogramStats 中从小到大，找到距离 v 最近的位置（用 cum_freq * table_rows 表示）
         - ET v: =v；等价于 LT v: v-，也即 v 的左起第一个。
         - GT v：v+，也即大于 v 的最小值，v + ε，也即大于 v 的第一个，也即 v 右边的第一个
         可能有很多 item 有相同的 v，但是从小到大（从左到右）找到第一个等于 v的结果就停止寻找，只会多一行，多一个这个可以忽略

        Args:
            value:
            [outdated] return_cum_freq: if True,返回 cum_freq * rows，否则仅返回 cum_freq
            histogram 本身仅考虑 cum_freq，不会用到 table_rows，table_rows 是 UT 妥协的产物，这里强制删除

        Returns:

        """
        value = convert_str_by_type(value, self.data_type, str_in_base4=False)  # histogram is base4 encoding，but request is raw string

        if value is None:
            return 0
        # convert to 0
        if value > self.buckets[-1].max_value:
            key_cum_freq = 1
        elif value < self.buckets[0].min_value:
            key_cum_freq = 0
        else:
            key_cum_freq = None
            for i in range(len(self.buckets)):
                if i < len(self.buckets) and (self.buckets[i].max_value < value < self.buckets[i + 1].min_value):
                    logging.warning(f"!!!!!!!!! value(={value})%s is "
                                    f"between buckets-{i} and {i + 1}: {self.buckets[i]}, {self.buckets[i + 1]}")
                    value = self.buckets[i].max_value
                cur: HistogramBucket = self.buckets[i]
                if cur.min_value <= value <= cur.max_value:
                    one_value_width: float  # [0, 1] 之间的浮点数，bucket 内一个值的宽度占比，1 是 bucket 全为这个值。
                    one_value_offset: float  # [0, 1] 之间的浮点数，bucket 内的相对位置比例（最左为 0，最右为 1）
                    # 暂不如此：我们在任何分布下，一个 bucket 内，一个值的最小宽度不小于 1 / bucket 内行数
                    # one_value_width = 1 / self.table_rows

                    # TODO 下面暂时采用均匀分布假设。
                    # 均匀分布下，认为一个值的宽度至少为 1 / bucket_ndv
                    one_value_width = 1 / cur.row_count
                    # 一个数字占 bucket 的宽度。
                    if cur.min_value == cur.max_value:
                        # assert self.histogram_type == 'singleton', "min=max should be singleton"
                        # 等宽，此时应该有 type=singleton
                        one_value_width, one_value_offset = 1, 0
                    else:
                        if data_type_is_int(self.data_type):
                            one_value_width = max(1 / (int(cur.max_value) - int(cur.min_value) + 1), one_value_width)
                            one_value_offset = (value - cur.min_value) / (cur.max_value + 1 - cur.min_value)
                        elif self.data_type in ['float', 'double', 'decimal']:
                            # 浮点数、decimal 暂时认为无限可微。但实际上 decimal 也有小数位数，char 也不是无限可微的
                            one_value_offset = (value - cur.min_value) / (cur.max_value - cur.min_value)
                        elif self.data_type in ['string']:
                            # 字符串仅支持比较，不支持加减，所以仅仅比较两端。非 min、max 的，暂定为 1/2
                            if value == cur.min_value:
                                one_value_offset = 0
                            elif value == cur.max_value:
                                one_value_offset = 1
                            else:
                                one_value_offset = 0.5
                        elif self.data_type in ['date']:
                            # 在 MySQL 中，DATE 类型的列只包含年月日部分，不包含时间（即时分秒）。
                            # MySQL 官方文档规定，日期值的格式应为 'YYYY-MM-DD'。但也可以支持YYYYMMDD, YY-MM-DD
                            # 甚至时间戳：SELECT L_SHIPDATE FROM lineitem WHERE FROM_UNIXTIME(1672531200) < L_SHIPDATE LIMIT 5;
                            # 但底层都会转化为 YYYY-MM-DD
                            # min_date = datetime.strptime(cur.min_value, '%Y-%m-%d')
                            # max_date = datetime.strptime(cur.max_value, '%Y-%m-%d')
                            # value_date = datetime.strptime(value, '%Y-%m-%d')
                            min_date = parse_datetime(cur.min_value)
                            max_date = parse_datetime(cur.max_value)
                            value_date = parse_datetime(value)

                            total_days = (max_date - min_date).days
                            one_value_width = max(1 / total_days, one_value_width)
                            one_value_offset = (value_date - min_date).days / total_days if total_days != 0 else 0

                        elif self.data_type in ['datetime']:
                            # datetime 包括时分秒，但格式也会被固定转化为 '2023-12-12 00:00:00'
                            min_datetime = parse_datetime(cur.min_value)
                            max_datetime = parse_datetime(cur.max_value)
                            value_datetime = parse_datetime(value)

                            total_seconds = int((max_datetime - min_datetime).total_seconds())
                            one_value_width = max(1 / total_seconds, one_value_width)
                            if total_seconds != 0:
                                one_value_offset = (value_datetime - min_datetime).total_seconds() / total_seconds
                            else:
                                one_value_offset = 0
                        else:
                            raise NotImplementedError(f"data_type {self.data_type} not supported")
                        # offset 是一个值的左边界。下面是考虑 one_value_offset 处于最右边界的情况
                        one_value_offset = min(one_value_offset, 1 - one_value_width)

                    if side == BTreeKeySide.left:
                        # key 左边，则直接是 one_value_offset
                        pos_in_bucket = one_value_offset
                    elif side == BTreeKeySide.right:
                        pos_in_bucket = one_value_offset + one_value_width
                    else:
                        raise ValueError(f"only support key pos side left and right, but get {side}")

                    pre_cum_freq = 0 if i == 0 else self.buckets[i - 1].cum_freq
                    key_cum_freq = pre_cum_freq + (cur.cum_freq - pre_cum_freq) * pos_in_bucket
                    break
        assert key_cum_freq is not None
        return key_cum_freq

    @staticmethod
    def init_from_mysql_json(data: dict):
        """
        这里的是指从 mysql 中拿出的原始数据，要做一些处理。和 to_json & from_json 不完全一样
        Args:
            data: 从 mysql 获得的原始 histogram

        Returns:

        """
        buckets: List[HistogramBucket] = []
        for bucket_raw in data['buckets']:
            bucket = init_bucket_by_type(bucket_raw, data['data-type'], data['histogram-type'])
            buckets.append(bucket)
        return HistogramStats(
            # table_rows=table_rows,
            buckets=buckets,
            data_type=data['data-type'],
            null_values=data['null-values'],
            collation_id=data.get('collation-id', None),
            last_updated=data.get('last-updated', None),
            sampling_rate=data.get('sampling-rate', MEANINGLESS_INT),  # a special value indicating no sampling rate
            histogram_type=data['histogram-type'],
            number_of_buckets_specified=data['number-of-buckets-specified']
        )


def query_histogram(env: Env, dbname: str, table_name: str, col_name: str) -> Union[HistogramStats, None]:
    """

    Args:
        dbname:
        table_name:
        col_name:

    Returns:

    """
    sql = f"SELECT HISTOGRAM FROM information_schema.column_statistics " \
          f"WHERE SCHEMA_NAME = '{dbname}' AND TABLE_NAME = '{table_name}' AND COLUMN_NAME ='{col_name}'"
    res = env.query_for_dataframe(sql)
    if len(res) == 0:
        return None
    assert len(res) == 1 and 'HISTOGRAM' in res.iloc[0].to_dict(), f"Invalid result from query_histogram: {res}"
    hist_dict = json.loads(res.iloc[0].to_dict()['HISTOGRAM'])

    return HistogramStats.init_from_mysql_json(data=hist_dict)


def update_histogram(env: Env, dbname: str, table_name: str, col_name: str,
                     n_buckets: int = 32, hist_mem_size: int = None) -> bool:
    """

    Args:
        env:
        dbname:
        table_name:
        col_name:
        n_buckets:

    Returns:
        success if return true

    """
    # n_buckets 取值范围仅为 [1, 1024]
    n_buckets = max(1, min(1024, int(n_buckets)))

    conn = env.mysql_util.get_connection()
    with conn.cursor() as cursor:
        if hist_mem_size is not None:
            cursor.execute(f'SET histogram_generation_max_mem_size={hist_mem_size};')
        sql = f"ANALYZE TABLE `{dbname}`.`{table_name}` UPDATE HISTOGRAM ON {col_name} WITH {n_buckets} BUCKETS;"
        logging.debug(sql)
        cursor.execute(sql)
        res = cursor.fetchone()
        if res is not None and len(res) == 4:
            if 'Histogram statistics created for column' in res[3]:
                return True
        conn.commit()

    raise Exception(f"meet error when query: {res}")


def drop_histogram(env: Env, dbname: str, table_name: str, col_name: str) -> bool:
    """

    Args:
        dbname:
        table_name:
        col_name:

    Returns:

    """
    sql = f"ANALYZE TABLE `{dbname}`.`{table_name}` DROP HISTOGRAM ON {col_name};"
    logging.debug(sql)
    res = env.query_for_dataframe(sql)
    if res is not None and len(res) == 1:
        msg = res.iloc[0].to_dict().get('Msg_text')
        return 'Histogram statistics removed for column' in msg
    return False


def get_bucket_bound(min_value, max_value, data_type, bucket_idx, n_buckets):
    """
    给定最大最小值、数据类型，返回 第 bucket_idx 个 buckets 的边界值
    Args:
        min_value:
        max_value:
        data_type:
        bucket_idx:
        n_buckets:

    Returns:

    """
    if bucket_idx == n_buckets:
        return max_value
    if data_type == 'datetime':
        # Assuming 'value' is a datetime object
        range_seconds = (max_value - min_value).total_seconds()
        bucket_seconds = range_seconds / n_buckets
        bucket_bound = min_value + timedelta(seconds=bucket_seconds * bucket_idx)
        return bucket_bound.strftime('%Y-%m-%d %H:%M:%S')
    elif data_type in ['char', 'varchar']:
        # Assuming 'value' is a string
        # For simplicity, we cut the string range into equal-length segments
        # This might not be accurate for highly uneven distributions
        min_val_ord = sum(map(ord, str(min_value)))
        max_val_ord = sum(map(ord, str(max_value)))
        range_ord = max_val_ord - min_val_ord
        bucket_ord = range_ord / n_buckets
        bucket_bound_ord = min_val_ord + bucket_ord * bucket_idx
        return ''.join(chr(int(bucket_bound_ord // len(str(min_value)))))
    else:
        # For other data types, return the value as is (numeric types, etc.)
        res = min_value + (max_value - min_value) * bucket_idx / n_buckets
        if data_type_is_int(data_type):
            res = int(res)
        return res


def force_generate_histogram_for_col_in_uk(env: Env, db_name: str, table_name: str, col_name: str,
                                           n_buckets: int, hist_mem_size: int = None) -> HistogramStats:
    """
    用暴力手段获取直方图，这可能是非常耗时的
    Args:
        env:
        db_name:
        table_name:
        col_name:
        n_buckets:
        hist_mem_size:

    Returns:
        initialize HistogramStats from json dict:
        {
            "buckets": [{
                    "min_value": "0000",
                    "max_value": "0000",
                    "cum_freq": 0.7035317292809906,
                    "row_count": 1
                },
            ],
            "data_type": None,
            "histogram_type": "brute_force_calc",
            "null_values": None,
            "collation_id": MEANINGLESS_INT,
            "sampling_rate": 1.0,
            "number_of_buckets_specified": None
        }
    """
    res_dict = {
        "buckets": [
        ],
        "data-type": None,
        "histogram-type": "brute_force_equi_width",  # 只能通过等宽边界来划分 bucket，因此是 qui-width
        "null-values": None,
        "collation-id": MEANINGLESS_INT,
        "sampling-rate": 1.0,
        "number-of-buckets-specified": None
    }
    column = env.get_column_meta(db_name, table_name, col_name)
    if not column:
        raise ValueError(f"column not found: {db_name}")
    data_type = column.data_type

    if data_type not in ['float', 'double', 'decimal'] and not data_type_is_int(data_type):
        # 尽管我们代码是支持的，但是 str 和 date 没有充分验证，因此这里要抛出错误，遇到问题及时修复
        raise NotImplementedError(f"not support data_type: {data_type} for now")

    # Find the minimum and maximum values in the column
    _df = env.query_for_dataframe(f"SELECT MIN({col_name}) as min, MAX({col_name}) as max FROM {db_name}.{table_name}")
    min_val, max_val = _df['min'][0], _df['max'][0]

    # Calculate the bucket size
    null_values = env.mysql_util.query_for_value(
        f"SELECT COUNT(1) FROM {db_name}.{table_name} WHERE {col_name} IS NULL;")
    total_rows = env.mysql_util.query_for_value(f"SELECT COUNT(1) FROM {db_name}.{table_name}")
    n_buckets = min(total_rows, n_buckets)
    if data_type_is_int(data_type):
        n_buckets = min(n_buckets, max_val - min_val + 1)

    res_dict['data-type'] = data_type
    res_dict['null-values'] = null_values

    if n_buckets == 0 or total_rows == 0:
        logging.warning(f"brute-force generate histogram, but meet 0: {n_buckets=} {total_rows=}")
        res_dict['number-of-buckets-specified'] = 0
        return HistogramStats.init_from_mysql_json(res_dict)

    res_dict['number-of-buckets-specified'] = n_buckets

    # Initialize the lower bound
    upper_bound = min_val

    # Calculate the cumulative frequency and NDV for each bucket
    cum_freq = 0
    for i in range(1, n_buckets + 1):
        if i % 10 == 0:
            logging.info(f"brute-force generate histogram [{i}/{n_buckets}] for {db_name}.{table_name} {col_name} ")
        if data_type_is_int(data_type) and n_buckets == max_val - min_val + 1:
            # 这是非常特殊的情况，对应 int singleton 的情况
            upper_bound = lower_bound = min_val + i - 1
            left_op = '>='
            right_op = '<='
        else:
            # Update the lower bound for the next bucket
            lower_bound = upper_bound
            # Define the upper bound of the bucket
            upper_bound = get_bucket_bound(min_val, max_val, data_type, i, n_buckets)
            # 当到达最右 buckets 时，应该囊括 max_value
            left_op = '>='
            right_op = '<=' if i == n_buckets else '<'

        # Query to get the count and NDV for the current bucket
        if data_type in ['string', 'str', 'date', 'datetime']:
            l_str = f"'{lower_bound}'"
            u_str = f"'{upper_bound}'"
        else:
            l_str = f"{lower_bound}"
            u_str = f"{upper_bound}"

        sql = f"""
                SELECT COUNT(1) as bucket_count, COUNT(DISTINCT {col_name}) as bucket_ndv,
                min({col_name}) as actual_min, max({col_name}) as actual_max 
                FROM {db_name}.{table_name}
                WHERE {col_name} {left_op} {l_str} AND {col_name} {right_op} {u_str}
            """
        _df = env.query_for_dataframe(sql)
        bucket_count, bucket_ndv = int(_df['bucket_count'][0]), int(_df['bucket_ndv'][0])

        # ndv 为 0 则该 buckets 无意义，跳过。各个 buckets 是左闭右闭区间，因此 buckets 边界不需要连续
        if bucket_ndv == 0:
            continue
        actual_min, actual_max = _df['actual_min'][0], _df['actual_max'][0]
        # print(f"{bucket_count=} {bucket_ndv=} {sql=}")

        # Calculate cumulative frequency
        cum_freq += bucket_count / total_rows

        # Add the histogram bucket details
        res_dict["buckets"].append([
            str(actual_min),
            str(actual_max),
            cum_freq,
            bucket_ndv,
        ])

    return HistogramStats.init_from_mysql_json(res_dict)


def fetch_col_histogram(env: Env, dbname: str, table_name: str, col_name: str, n_buckets: int = 32,
                        force: bool = False, hist_mem_size: int = None) -> HistogramStats:
    """
    查询或生成指定一列的 histogram
    Args:
        env: MySQL 连接
        dbname: 数据库名
        table_name: 表名
        col_name: 列名
        n_buckets: 桶的数量，默认为 32
        force: 是否强制生成，默认为 False

    Returns:

    """
    # 如果不是强制生成，且 mysql 中已经有了，则直接返回
    if not force:
        hist: HistogramStats = query_histogram(env, dbname, table_name, col_name)
        if hist is not None:
            if len(hist.buckets) == n_buckets:
                return hist
            else:
                logging.debug(f"hist(`{dbname}`.`{table_name}`.`{col_name=}`) exists, "
                              f"but n_bucket mismatch (exists={len(hist.buckets)} != {n_buckets}), re-generate.")
        else:
            logging.debug(f"Histogram(`{dbname}`.`{table_name}`.`{col_name=}`) not found. "
                          f"Generating with {n_buckets} n_buckets")
    else:
        logging.debug(
            f"Force Generating Histogram for `{dbname}`.`{table_name}`.`{col_name}` with {n_buckets} n_buckets")
    # 生成并返回
    try:
        res_update = update_histogram(env, dbname, table_name, col_name, n_buckets, hist_mem_size)
    except Exception as e:
        if 'is covered by a single-part unique index' in str(e):
            # 由于 col 属于 uk，因此不能创建，执行特殊处理。否则，继续抛出
            logging.info(f"Column is covered single uk, force generate: {dbname=}, {table_name=}, {col_name=}")
            return force_generate_histogram_for_col_in_uk(env, dbname, table_name, col_name, n_buckets)
        else:
            logging.error(f"uncatched: {dbname=}, {table_name=}, {col_name=}")
            raise
    assert res_update, 'Failed to update histogram'
    return query_histogram(env, dbname, table_name, col_name)


def generate_fetch_histogram(env: Env, target_db: str, all_table_names: List[str],
                             n_buckets: int, force: bool,
                             drop_hist_after_fetch: bool,
                             hist_mem_size: int,
                             ret_json: bool = False,
                             table_col_dict: dict = None,
                             ) -> Dict[str, Dict[str, Union[HistogramStats, dict]]]:
    """
    为指定表的所有列生成并返回 histogram

    Args:
        env: MySQL 连接
        target_db: 目标数据库名
        all_table_names: 所有要生成的表
        n_buckets: 桶的数量
        force: 是否强制生成，默认为 False
        ret_json: True: 每个直方图返回 json 格式，False: 返回 HistogramStats 格式
        table_col_dict: table_name -> col。如果非空，则仅

    Returns:
        lower_table -> column -> HistogramStats

    """
    if not target_env_available_for_videx(env):
        raise Exception(f"given env ({env.instance=}) is not in BLACKLIST, cannot generate_fetch_histogram directly")

    res_tables = defaultdict(dict)
    for table_name in all_table_names:
        table_meta: Table = env.get_table_meta(target_db, table_name)
        # print(table_meta)
        for c_id, col in enumerate(table_meta.columns):
            col: Column
            try:
                logging.info(f"Generating Histogram for `{target_db}`.`{table_name}`.`{col.name}` "
                             f"with {n_buckets} n_buckets")
                hist = fetch_col_histogram(env, target_db, table_name, col.name, n_buckets, force=force,
                                           hist_mem_size=hist_mem_size)
            finally:
                # 可能被用户手动杀死，但仍然要 drop 掉，避免残留 histogram 对 videx 的影响
                if drop_hist_after_fetch:
                    drop_histogram(env, target_db, table_name, col.name)

            if hist is not None and ret_json:
                hist = hist.to_dict()
            res_tables[str(table_name).lower()][col.name] = hist
    return res_tables


if __name__ == '__main__':
    pass
