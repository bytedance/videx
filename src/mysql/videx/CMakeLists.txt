# Copyright (c) 2024 Bytedance Ltd. and/or its affiliates
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License, version 2.0,
# as published by the Free Software Foundation.
#
# This program is also distributed with certain software (including
# but not limited to OpenSSL) that is licensed under separate terms,
# as designated in a particular file or component or in included license
# documentation.  The authors of MySQL hereby grant you an additional
# permission to link the program and your derivative works with the
# separately licensed software that they have included with MySQL.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License, version 2.0, for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301  USA

DISABLE_MISSING_PROFILE_WARNING()
ADD_DEFINITIONS(-DMYSQL_SERVER)
ADD_DEFINITIONS(-DMUTEX_FUTEX)

INCLUDE_DIRECTORIES(
        ${CMAKE_SOURCE_DIR}/sql
        ${CMAKE_SOURCE_DIR}/sql/auth
        ${CMAKE_SOURCE_DIR}/storage/innobase/include
        ${CMAKE_SOURCE_DIR}/storage/innobase
        ${CMAKE_SOURCE_DIR}/extra/rapidjson/include
        ${CMAKE_SOURCE_DIR}/extra/curl/curl-8.1.2/include
)

IF(WITH_VIDEX_STORAGE_ENGINE AND NOT WITHOUT_VIDEX_STORAGE_ENGINE)
  MYSQL_ADD_PLUGIN(VIDEX
    videx_json_item.cc
    videx_log_utils.cc
    ha_videx.cc
    STORAGE_ENGINE
    DEFAULT
    LINK_LIBRARIES ext::zlib ext::curl  # 添加这里
    # ${CMAKE_SOURCE_DIR}/sql/videx_info_global.cc  # 添加此行
    )
ELSEIF(NOT WITHOUT_VIDEX_STORAGE_ENGINE)
  MYSQL_ADD_PLUGIN(VIDEX
    videx_json_item.cc
    videx_log_utils.cc
    ha_videx.cc
    STORAGE_ENGINE
    MODULE_ONLY
    LINK_LIBRARIES ext::zlib ext::curl  # 添加这里
    # ${CMAKE_SOURCE_DIR}/sql/videx_info_global.cc  # 添加此行
    )
ENDIF()

ADD_DEPENDENCIES(videx innobase)
