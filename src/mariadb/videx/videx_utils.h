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

/** @file videx_utils.h
 *
 * @brief
 * Lightweight JSON utilities for MariaDB storage engine development:
 * - VidexJsonItem class: Hierarchical JSON builder.
 * - Simple parser: Extracts code/message/data from flat JSON structures, at most 2-level nested.
 * @note
 * 1. Parser supports max 2-level nested JSON structures
 * 2. Builder automatically escapes special characters (\"\\)
 * 3. Use construct_request() for standard API request templates
 * 4. Cross-platform: Avoids rapid_json segmentation faults on macOS
 * 5. Serializes key_range to JSON object
 *
 * @see
 * - Implementation: videx_utils.cc
 */


#ifndef VIDEX_UTILS
#define VIDEX_UTILS

#include <my_global.h>
#include <unordered_map>
#include <vector>
#include <iostream>
#include <sstream>
#include <string>
#include <my_base.h>
#include <key.h>
#include <structs.h>
#include <field.h>
#include <table.h>
#include <mysqld.h>
#include <map>
#include <stdexcept>
#include <stdio.h>
#include <string.h>
#include <climits>
#include <list>
#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <memory>
#include <sql_string.h>
#include <fstream>

typedef std::map<std::string, std::string> VidexStringMap;

static inline bool videx_contains_key(const VidexStringMap &myMap,
                               const std::string &key)
{
  return myMap.find(key) != myMap.end();
}

/*
  Numeric conversion helpers for values coming from the statistic server.

  The response values are plain strings, so a structurally valid response can
  still carry a value that is empty, non-numeric, negative for an unsigned
  field, or out of range. Calling std::sto* directly on those is unsafe in two
  distinct ways:

    - it throws std::invalid_argument / std::out_of_range, and a C++ exception
      must not escape a storage engine callback;
    - worse, some inputs do not throw at all and are silently accepted:
      std::stoull("-1") wraps to 18446744073709551615, std::stoull("12abc")
      returns 12, and std::stoull("0x10") returns 0.

  The helpers below reject both cases. They return false and leave the output
  parameter untouched, so every caller can keep using its existing fallback.
*/

static inline bool videx_parse_find_first_char(const std::string &str,
                                               size_t &begin)
{
  begin= str.find_first_not_of(" \t\n\r\f\v");
  return begin != std::string::npos;
}

/** Return true when str holds nothing but trailing whitespace from pos on. */
static inline bool videx_parse_only_trailing_space(const std::string &str,
                                                   size_t pos)
{
  return str.find_first_not_of(" \t\n\r\f\v", pos) == std::string::npos;
}

/**
 * Parse an unsigned 64-bit value. Rejects empty, non-numeric, negative,
 * trailing-garbage and out-of-range input.
 * @return true on success; on failure returns false and leaves `out` unchanged.
 */
static inline bool videx_try_parse_ull(const std::string &str,
                                       unsigned long long &out)
{
  size_t begin= 0;
  if (!videx_parse_find_first_char(str, begin))
    return false;
  // std::stoull accepts a leading '-' and wraps around; reject it explicitly.
  if (str[begin] == '-')
    return false;
  try
  {
    size_t pos= 0;
    unsigned long long value= std::stoull(str, &pos);
    if (!videx_parse_only_trailing_space(str, pos))
      return false;
    out= value;
    return true;
  }
  catch (const std::invalid_argument &)
  {
    return false;
  }
  catch (const std::out_of_range &)
  {
    return false;
  }
}

/** Parse an unsigned long, additionally rejecting values that do not fit. */
static inline bool videx_try_parse_ul(const std::string &str,
                                      unsigned long &out)
{
  unsigned long long value= 0;
  if (!videx_try_parse_ull(str, value))
    return false;
  if (value > (unsigned long long) ULONG_MAX)
    return false;
  out= (unsigned long) value;
  return true;
}

/** Parse a double. Rejects trailing garbage, which std::stod would accept. */
static inline bool videx_try_parse_double(const std::string &str, double &out)
{
  size_t begin= 0;
  if (!videx_parse_find_first_char(str, begin))
    return false;
  try
  {
    size_t pos= 0;
    double value= std::stod(str, &pos);
    if (!videx_parse_only_trailing_space(str, pos))
      return false;
    out= value;
    return true;
  }
  catch (const std::invalid_argument &)
  {
    return false;
  }
  catch (const std::out_of_range &)
  {
    return false;
  }
}

int videx_parse_simple_json(const std::string &json, int &code,
                            std::string &message,
                            std::map<std::string, std::string> &data_dict);

std::string videx_escape_double_quotes(const std::string &input,
                                       size_t len= std::string::npos);

class VidexJsonItem
{
public:
  std::string item_type;
  std::map<std::string, std::string> properties;
  std::list<VidexJsonItem> data;
  int depth;

  VidexJsonItem() : item_type("empty"), depth(0) {}

  VidexJsonItem(const std::string &item_type, int depth)
      : item_type(item_type), depth(depth) {}

  VidexJsonItem *create(const std::string &new_item_type);

  VidexJsonItem *create(const std::string &item_type, const char *prompt);

  void add_property(const std::string &key, const std::string &value);

  void add_property(const std::string &key, const char *value);

  void add_property(const std::string &key, const String &value);

  void add_property(const std::string &key, const String *value);

  // Except for string which might be empty and needs to be converted to NULL
  // separately, all other values can be handled using this function.
  template <typename V>
  void add_property_nonan(const std::string &key, V value)
  {
    std::stringstream ss;
    ss << value;
    properties[key]= ss.str();
  }

  std::string to_json() const;
};

/**
construct a basic request, and other parameters can be conveniently added
externally. */

static inline VidexJsonItem
construct_request(const std::string &db_name, const std::string &table_name,
                  const std::string &function,
                  const std::string &target_storage_engine= "INNODB")
{
  VidexJsonItem req("videx_request", 0);
  req.add_property("dbname", db_name);
  req.add_property("table_name", table_name);
  req.add_property("function", function);
  req.add_property("target_storage_engine", target_storage_engine);
  return req;
}

/**
  Serializes min/max key bounds for a given index into `req_json`.
  Also prints a concise human-readable summary for debugging.

  @param min_key Minimum key range.
  @param max_key Maximum key range.
  @param key Index key information.
  @param req_json JSON object to store serialized key range.
*/
void serializeKeyRangeToJson(const key_range *min_key,
                             const key_range *max_key, KEY *key,
                             VidexJsonItem *req_json);

#endif // VIDEX_UTILS
