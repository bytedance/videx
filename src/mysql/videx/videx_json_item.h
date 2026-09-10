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

#ifndef VIDEX_JSON_ITEM_H
#define VIDEX_JSON_ITEM_H

#include <iostream>
#include <string>
#include <map>
#include <sstream>
#include <stdexcept>
#include <stdio.h>
#include <string.h>
#include <climits>
#include <cfloat>
#include <unordered_map>
#include <list>
#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <memory>
#include "sql_string.h"
#include <fstream>

typedef std::map<std::string, std::string> VidexStringMap;

inline bool videx_contains_key(const VidexStringMap &myMap, const std::string &key) {
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

inline bool videx_parse_find_first_char(const std::string &str, size_t &begin) {
    begin = str.find_first_not_of(" \t\n\r\f\v");
    return begin != std::string::npos;
}

/** Return true when str holds nothing but trailing whitespace from pos on. */
inline bool videx_parse_only_trailing_space(const std::string &str, size_t pos) {
    return str.find_first_not_of(" \t\n\r\f\v", pos) == std::string::npos;
}

/**
 * Parse an unsigned 64-bit value. Rejects empty, non-numeric, negative,
 * trailing-garbage and out-of-range input.
 * @return true on success; on failure returns false and leaves `out` unchanged.
 */
inline bool videx_try_parse_ull(const std::string &str, unsigned long long &out) {
    size_t begin = 0;
    if (!videx_parse_find_first_char(str, begin)) return false;
    // std::stoull accepts a leading '-' and wraps around; reject it explicitly.
    if (str[begin] == '-') return false;
    try {
        size_t pos = 0;
        unsigned long long value = std::stoull(str, &pos);
        if (!videx_parse_only_trailing_space(str, pos)) return false;
        out = value;
        return true;
    } catch (const std::invalid_argument &) {
        return false;
    } catch (const std::out_of_range &) {
        return false;
    }
}

/** Parse an unsigned long, additionally rejecting values that do not fit. */
inline bool videx_try_parse_ul(const std::string &str, unsigned long &out) {
    unsigned long long value = 0;
    if (!videx_try_parse_ull(str, value)) return false;
    if (value > static_cast<unsigned long long>(ULONG_MAX)) return false;
    out = static_cast<unsigned long>(value);
    return true;
}

/** Parse a signed 64-bit value. A leading '-' is valid here. */
inline bool videx_try_parse_ll(const std::string &str, long long &out) {
    size_t begin = 0;
    if (!videx_parse_find_first_char(str, begin)) return false;
    try {
        size_t pos = 0;
        long long value = std::stoll(str, &pos);
        if (!videx_parse_only_trailing_space(str, pos)) return false;
        out = value;
        return true;
    } catch (const std::invalid_argument &) {
        return false;
    } catch (const std::out_of_range &) {
        return false;
    }
}

/** Parse a double. Rejects trailing garbage, which std::stod would accept. */
inline bool videx_try_parse_double(const std::string &str, double &out) {
    size_t begin = 0;
    if (!videx_parse_find_first_char(str, begin)) return false;
    try {
        size_t pos = 0;
        double value = std::stod(str, &pos);
        if (!videx_parse_only_trailing_space(str, pos)) return false;
        out = value;
        return true;
    } catch (const std::invalid_argument &) {
        return false;
    } catch (const std::out_of_range &) {
        return false;
    }
}

/** Parse a float, reusing the double parser and rejecting overflow. */
inline bool videx_try_parse_float(const std::string &str, float &out) {
    double value = 0;
    if (!videx_try_parse_double(str, value)) return false;
    if (value > static_cast<double>(FLT_MAX) ||
        value < -static_cast<double>(FLT_MAX)) {
        return false;
    }
    out = static_cast<float>(value);
    return true;
}

int videx_parse_simple_json(const std::string &json, int &code, std::string &message,
                      std::map<std::string, std::string> &data_dict);


std::string videx_escape_double_quotes(const std::string &input,
                               size_t len = std::string::npos);

class VidexJsonItem {
public:
    std::string item_type;
    std::map<std::string, std::string> properties;
    std::list<VidexJsonItem> data;
    int depth;

    VidexJsonItem()
            : item_type("empty"), depth(0) {}

    /// specify item_type
    VidexJsonItem(const std::string &item_type, int depth)
            : item_type(item_type), depth(depth) {}

    /// create a new VidexJsonItem，插入data，然后返回这个VidexJsonItem的引用
    VidexJsonItem *create(const std::string &new_item_type) {
        data.push_back(VidexJsonItem(new_item_type, depth + 1));
        return &data.back();
    }

    VidexJsonItem *create(const std::string &item_type, const char *prompt) {
        VidexJsonItem newOne = VidexJsonItem(item_type, depth + 1);
        newOne.add_property("prompt", prompt);
        data.push_back(newOne);
        return &data.back();
    }

    /// add to properties
    void add_property(const std::string &key, const std::string &value) {
        properties[key] = videx_escape_double_quotes(value);
    }

    void add_property(const std::string &key, const char *value) {
        if (value != NULL) {
            properties[key] = videx_escape_double_quotes(value);
        } else {
            properties[key] = "NULL";
        }
    }

    void add_property(const std::string &key, const Simple_cstring &value) {
        if (value.is_set() && value.ptr() != NULL) {
            properties[key] = videx_escape_double_quotes(value.ptr(), value.length());
        } else {
            properties[key] = "NULL";
        }
    }

    void add_property(const std::string &key, const String &value) {
        if (!value.is_alloced() || !value.ptr() || !value.alloced_length() ||
            (value.alloced_length() < (value.length() + 1))) {
            properties[key] = "NULL";
        } else {
            properties[key] = videx_escape_double_quotes(value.ptr(), value.length());
        }
    }

    void add_property(const std::string &key, const String *value) {
        if (value == NULL) {
            properties[key] = "NULL";
        } else {
            add_property(key, *value);
        }
    }

    template<typename V>
    // Except for string which might be empty and needs to be converted to NULL separately,
    // all other values can be handled using this function.
    void add_property_nonan(const std::string &key, V value) {
        std::stringstream ss;
        ss << value;
        properties[key] = ss.str();
    }

    std::string to_json() const {
        std::string json = "{";

        json += "\"item_type\":\"" + item_type + "\",";

        json += "\"properties\":{";
        for (std::map<std::string, std::string>::const_iterator it =
                properties.begin();
             it != properties.end(); ++it) {
            json += "\"" + it->first + "\":\"" + it->second + "\",";
        }
        if (!properties.empty()) {
            json.erase(json.length() - 1);  // remove trailing comma
        }
        json += "},";

        json += "\"data\":[";
        for (std::list<VidexJsonItem>::const_iterator it = data.begin();
             it != data.end(); ++it) {
            json += it->to_json() + ",";
        }
        if (!data.empty()) {
            json.erase(json.length() - 1);  // remove trailing comma
        }
        json += "]}";

        return json;
    }
};

/**
 * construct a basic request, and other parameters can be conveniently added externally.
*/
inline VidexJsonItem construct_request(const std::string &db_name,
                                       const std::string &table_name,
                                       const std::string &function,
                                       const std::string &target_storage_engine = "INNODB") {
    VidexJsonItem req("videx_request", 0);
    req.add_property("dbname", db_name);
    req.add_property("table_name", table_name);
    req.add_property("function", function);
    req.add_property("target_storage_engine", target_storage_engine);
    return req;
}

#endif  // VIDEX_JSON_ITEM_H
