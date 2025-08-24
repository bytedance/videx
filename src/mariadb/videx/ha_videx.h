/* Copyright (c) 2025 Bytedance Ltd. and/or its affiliates

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

/**
VIDEX storage engine header.
See also `storage/videx/ha_videx.cc` and `sql/handler.h`.
*/

#include "my_global.h"                   /* ulonglong */
#include "thr_lock.h"                    /* THR_LOCK, THR_LOCK_DATA */
#include "handler.h"                     /* handler */
#include "my_base.h"                     /* ha_rows */
#include "table.h"
#include <sql_acl.h>
#include <sql_class.h>
#include <my_sys.h>
#include "scope.h"
#include <my_service_manager.h>
#include "videx_json_item.h"
#include "videx_log_utils.h"
#include <replication.h>
#include <curl/curl.h>

/** Shared state used by all open VIDEX handlers. */
class videx_share : public Handler_share {
public:
	mysql_mutex_t mutex;
	THR_LOCK lock;
	videx_share();
	~videx_share()
	{
		thr_lock_delete(&lock);
		mysql_mutex_destroy(&mutex);
	}
};

/** Storage engine class. */
class ha_videx: public handler
{
	THR_LOCK_DATA lock;
	videx_share *share;
	videx_share *get_share();

public:
	ha_videx(handlerton* hton, TABLE_SHARE* table_arg);
	~ha_videx() override;

	const char* table_type() const override;

	Table_flags table_flags() const override;

	ulong index_flags(uint idx, uint part, bool all_parts) const override;

	uint max_supported_keys() const override;

	uint max_supported_key_length() const override;

	uint max_supported_key_part_length() const override;

	const key_map* keys_to_use_for_scanning() override;

	void column_bitmaps_signal() override;

	int open(const char *name, int mode, uint test_if_locked) override;

	handler* clone(const char *name, MEM_ROOT *mem_root) override;

	int close(void) override;

	IO_AND_CPU_COST scan_time() override;
	
	IO_AND_CPU_COST rnd_pos_time(ha_rows rows) override;

	int write_row(const uchar * buf) override;

	int update_row(const uchar * old_data, const uchar * new_data) override;

	int delete_row(const uchar * buf) override;

	void unlock_row() override;

	int index_next(uchar * buf) override;

	int index_prev(uchar * buf) override;

	int index_first(uchar * buf) override;

	int index_last(uchar * buf) override;

	int rnd_init(bool scan) override;

	int rnd_end() override;

	int rnd_next(uchar *buf) override;

	int rnd_pos(uchar * buf, uchar *pos) override;

	void position(const uchar *record) override;

	int info(uint) override;

	int extra(ha_extra_function operation) override;

	int reset() override;

	int external_lock(THD *thd, int lock_type) override;

	THR_LOCK_DATA** store_lock(
		THD*			thd,
		THR_LOCK_DATA**		to,
		thr_lock_type		lock_type) override;

	ha_rows records_in_range(
		uint                    inx,
		const key_range*        min_key,
		const key_range*        max_key,
		page_range*             pages) override;

	int create(
		const char*		name,
		TABLE*			form,
		HA_CREATE_INFO*		create_info) override;

	int delete_table(const char *name) override;

	int rename_table(const char* from, const char* to) override;

	int multi_range_read_init(
		RANGE_SEQ_IF*		seq,
		void*			seq_init_param,
		uint			n_ranges,
		uint			mode,
		HANDLER_BUFFER*		buf) override;

	int multi_range_read_next(range_id_t *range_info) override;

	ha_rows multi_range_read_info_const(
		uint			keyno,
		RANGE_SEQ_IF*		seq,
		void*			seq_init_param,
		uint			n_ranges,
		uint*			bufsz,
		uint*			flags,
		ha_rows                 limit,
		Cost_estimate*		cost) override;

	ha_rows multi_range_read_info(uint keyno, uint n_ranges, uint keys,
		uint key_parts, uint* bufsz, uint* flags,
		Cost_estimate* cost) override;

	int multi_range_read_explain_info(uint mrr_mode, char *str, size_t size) override;

	Item* idx_cond_push(uint keyno, Item* idx_cond) override;
  
	int info_low(uint flag, bool is_analyze);

	/** The multi range read session object */
	DsMrr_impl m_ds_mrr;
	
	/** Thread handle of the user currently using the handler;
	this is set in external_lock function */
	THD *m_user_thd;

	/** Flags that specificy the handler instance (table) capability. */
	Table_flags m_int_table_flags;

	/** Index into the server's primary key meta-data table->key_info{} */
	uint m_primary_key;

	/** this is set to 1 when we are starting a table scan but have
	not yet fetched any row, else false */
	bool m_start_of_scan;
	
	/** If mysql has locked with external_lock() */
	bool m_mysql_has_locked;
};

typedef float rec_per_key_t;