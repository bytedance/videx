/* Copyright (c) 2024 Bytedance Ltd. and/or its affiliates

  This program is free software; you can redistribute it and/or modify
  it under the terms of the GNU General Public License, version 2.0,
  as published by the Free Software Foundation.

  This program is also distributed with certain software (including
  but not limited to OpenSSL) that is licensed under separate terms,
  as designated in a particular file or component or in included license
  documentation.  The authors of MySQL hereby grant you an additional
  permission to link the program and your derivative works with the
  separately licensed software that they have included with MySQL.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License, version 2.0, for more details.

  You should have received a copy of the GNU General Public License
  along with this program; if not, write to the Free Software
  Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301  USA */

#include "videx_log_utils.h"
#include <mysql/service_thd_alloc.h>

/**
Return printable field name; MariaDB 11.0 lacks functional index names.
*/

const char *get_field_name_or_expression(THD *, const Field *field) {
    return field->field_name.str;
}

VidexLogUtils videx_log_ins;

/**
Mark unexpected call-sites for debugging; prints a short message.
*/

void VidexLogUtils::markPassbyUnexpected(const std::string &func,
                                           const std::string &file,
                                           const int line) {
  markHaFuncPassby(func, file, line, "NOOOO!", true);
}

/**
Explicitly suppress logging for known-irrelevant call paths during EXPLAIN.
*/

void VidexLogUtils::NotMarkPassby(const std::string &, const std::string &,
                                    const int) {
  // For things that are explicitly known to be unrelated to the query but will be used during explain,
  // use this function. Actually, nothing is printed.
  return;
}

/**
Generic passby logger with optional message and silence flag.
*/

void VidexLogUtils::markHaFuncPassby(const std::string &func,
                                       const std::string &file, const int line,
                                       const std::string &others, bool silent) {
  count++;
  if (silent) {
    return;
  }
  std::stringstream ss;
  ss << "VIDEX_PASSBY[" << count << "]<" << this->tag << "> ";
  if (!others.empty()) {
    ss << "___MSG:{" << others << "} ";
  }

  ss << " ____ " << func << " ____ File: " << file << ":" << line;
  if (enable_cout) {
    std::cout << ss.str() << std::endl;
  }
  if (enable_trace) {
    // TODO not support for now, need to set thd and initialize trace_object
  }
}


/**
  Print a key to a string
  referring to print_key_value - sql/range_optimizer/range_optimizer.cc:1429

  @param[out] out          String the key is appended to
  @param[in]  key_part     Index components description
  @param[in]  key          Key tuple
*/

void videx_print_key_value(String *out, const KEY_PART_INFO *key_part,
                           const uchar *uchar_key) {
    Field *field = key_part->field;

    if (field->flags & BLOB_FLAG) {
        // Byte 0 of a nullable key is the null-byte. If set, key is NULL.
        if (field->maybe_null() && *uchar_key) {
          out->append(STRING_WITH_LEN("NULL"));
          return;
        }
        else
            if (field->type() == MYSQL_TYPE_GEOMETRY) {
              out->append(STRING_WITH_LEN("unprintable_geometry_value"));
              return;
            } else {
              // if uncomment, videx will return fixed "unprintable_blob_value"
              // out->append(STRING_WITH_LEN("unprintable_blob_value"));
              // return;
            }
    }

    uint store_length = key_part->store_length;

    if (field->maybe_null()) {
        /*
          Byte 0 of key is the null-byte. If set, key is NULL.
          Otherwise, print the key value starting immediately after the
          null-byte
        */
        if (*uchar_key) {
            out->append(STRING_WITH_LEN("NULL"));
            return;
        }
        uchar_key++;  // Skip null byte
        store_length--;
    }

    /*
      Binary data cannot be converted to UTF8 which is what the
      optimizer trace expects. If the column is binary, the hex
      representation is printed to the trace instead.
    */
    if (field->result_type() == STRING_RESULT &&
        field->charset() == &my_charset_bin) {
        out->append(STRING_WITH_LEN("0x"));
        for (uint i = 0; i < store_length; i++) {
            out->append(_dig_vec_lower[*(uchar_key + i) >> 4]);
            out->append(_dig_vec_lower[*(uchar_key + i) & 0x0F]);
        }
        return;
    }

    StringBuffer<128> tmp(system_charset_info);
    bool add_quotes = field->result_type() == STRING_RESULT;

    TABLE *table = field->table;
    MY_BITMAP *old_sets[2];

    dbug_tmp_use_all_columns(table, old_sets, &table->read_set, &table->write_set);

    field->set_key_image(uchar_key, key_part->length);
    if (field->type() == MYSQL_TYPE_BIT) {
        (void)field->val_int_as_str(&tmp, true);  // may change tmp's charset
        add_quotes = false;
    } else {
        field->val_str(&tmp);  // may change tmp's charset
    }

    dbug_tmp_restore_column_maps(&table->read_set, &table->write_set, old_sets);

    if (add_quotes) {
        out->append('\'');
        // Worst case: Every character is escaped.
        const size_t buffer_size = tmp.length() * 2 + 1;
        char *quoted_string = (char*)thd_alloc(current_thd, buffer_size);

        my_bool overflow;
        const size_t quoted_length = escape_string_for_mysql(
                tmp.charset(), quoted_string, buffer_size, tmp.ptr(), tmp.length(), &overflow);
        if (overflow) {
            // Overflow. Our worst case estimate for the buffer size was too low.
            assert(false);
            return;
        }
        out->append(quoted_string, quoted_length, tmp.charset());
        out->append('\'');
    } else {
        out->append(tmp.ptr(), tmp.length(), tmp.charset());
    }
}

/**
Convert range read function to a concise symbolic operator string.
*/

std::string haRKeyFunctionToSymbol(ha_rkey_function function) {
    switch (function) {
        case HA_READ_KEY_EXACT:
            return "=";
        case HA_READ_KEY_OR_NEXT:
            return ">=";
        case HA_READ_KEY_OR_PREV:
            return "<=";
        case HA_READ_AFTER_KEY:
            return ">";
        case HA_READ_BEFORE_KEY:
            return "<";
        case HA_READ_PREFIX:
            return "=x%";
        case HA_READ_PREFIX_LAST:
            return "last_x%";
        case HA_READ_PREFIX_LAST_OR_PREV:
            return "<=last_x%";
        case HA_READ_MBR_CONTAIN:
            return "HA_READ_MBR_CONTAIN";
        case HA_READ_MBR_INTERSECT:
            return "HA_READ_MBR_INTERSECT";
        case HA_READ_MBR_WITHIN:
            return "HA_READ_MBR_WITHIN";
        case HA_READ_MBR_DISJOINT:
            return "HA_READ_MBR_DISJOINT";
        case HA_READ_MBR_EQUAL:
            return "HA_READ_MBR_EQUAL";
        default:
            return "Unknown ha_rkey_function";
    }
}

/**
Append one column bound to output and JSON; used by key-range serialization.
*/

inline void subha_append_range(String *out, const KEY_PART_INFO *key_part,
                               const uchar *uchar_key,
                               const uint, VidexJsonItem* range_json) {
    if (out->length() > 0) out->append(STRING_WITH_LEN("  "));
    String tmp_str;
    tmp_str.set_charset(system_charset_info);
    tmp_str.length(0);
    std::stringstream ss;

    const char * field_or_expr = get_field_name_or_expression(current_thd, key_part->field);
    out->append(field_or_expr, strlen(field_or_expr));
    range_json->add_property("column", field_or_expr);

    out->append(STRING_WITH_LEN("("));
    videx_print_key_value(&tmp_str, key_part, uchar_key);
    out->append(tmp_str);
    out->append(STRING_WITH_LEN("), "));
    ss.write(tmp_str.ptr(), tmp_str.length());
    range_json->add_property("value", ss.str());
    tmp_str.length(0);
}

/**
Return indices of set bits (0..63) in the given bitmap.
*/

std::vector<int> BitsSetIn(ulong bitmap) {
    std::vector<int> result;
    for (int i = 0; i < 64; ++i) {
        if (bitmap & (1UL << i)) result.push_back(i);
    }
    return result;
}

/**
Serialize a `key_range` into text and JSON; mirrors range optimizer output.
*/

void subha_parse_key_range(const key_range *key_range, const KEY *index,
                           String *out, VidexJsonItem *req_json) {
    const uint QUICK_RANGE_flag = -1;
    if (key_range == nullptr) {
        out->append(STRING_WITH_LEN("<NO_KEY_RANGE>"));
        return;
    }
    KEY_PART_INFO *first_key_part = index->key_part;
    out->append(STRING_WITH_LEN(" "));
    std::string key_range_flag_str = haRKeyFunctionToSymbol(key_range->flag);
    out->append(key_range_flag_str.c_str(), key_range_flag_str.length());

    req_json->add_property("operator", key_range_flag_str);
    req_json->add_property_nonan("length", key_range->length);
    req_json->add_property("index_name", index->name.str);

    const uchar *uchar_key = key_range->key;
    for (int keypart_idx : BitsSetIn(key_range->keypart_map)) {
        VidexJsonItem *range_json = req_json->create("column_and_bound");
        subha_append_range(out, &first_key_part[keypart_idx], uchar_key,
                           QUICK_RANGE_flag, range_json);

        uchar_key += first_key_part[keypart_idx].store_length;
    }
}

/**
Logs and serializes min/max key bounds for a given index into `req_json`.
Also prints a concise human-readable summary for debugging.
*/

void VidexLogUtils::markRecordInRange([[maybe_unused]]const std::string &func, [[maybe_unused]]const std::string &file,
                                       [[maybe_unused]]const int line, const key_range *min_key, const key_range *max_key,
                                       KEY *key, VidexJsonItem *req_json) {
    String range_info;
    range_info.set_charset(system_charset_info);

    VidexJsonItem* min_json = req_json->create("min_key");
    subha_parse_key_range(min_key, key, &range_info, min_json);
    std::string std_info_min(range_info.ptr(), range_info.length());
    range_info.length(0);

    VidexJsonItem* max_json = req_json->create("max_key");
    subha_parse_key_range(max_key, key, &range_info, max_json);
    std::string std_info_max(range_info.ptr(), range_info.length());
    range_info.length(0);

    std::stringstream ss;
    ss << "KEY: " << key->name.str << "   MIN_KEY: {" << std_info_min << "}, MAX_KEY: {"<<std_info_max << "}";
    std::cout << std::endl << ss.str() << std::endl;
    std::cout << "req_json = " << req_json->to_json() << std::endl;
}
