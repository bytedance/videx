### Videx For Postgresql

Videx-for-pg is developing in the form of a PostgreSQL plugin...
1. already support  local test without videx-statistic-server.
2. [wip] run with videx-statistic-server

### Qucik Start Without Videx-Statistic-Server
##### step1: compile videx
1. Copy the pg/videx folder to the contrib folder in your pg directory (such as postgresql17.5)
2. go into postgresql17.5/contrib/videx: 
`make && make install`

##### step2：register videx in pg
1. go to postgresql.conf:
`shared_preload_libraries = 'videx'		# (change requires restart)`
2. start your pg service and psql:
`create extension videx;`

	```sql
		/*Verify if the registration was successful*/
		test=# SELECT * FROM pg_extension WHERE extname = 'videx';
		  oid   | extname | extowner | extnamespace | extrelocatable | extversion | extconfig | extcondition 
		--------+---------+----------+--------------+----------------+------------+-----------+--------------
		 368789 | videx   |       10 |         2200 | t              | 1.0        |           | 
		(1 row)
	```

#### step3: use videx
1. create videx table using videx storage
`CREATE TABLE V_REGION (
	R_REGIONKEY	SERIAL,
	R_NAME		CHAR(25),
	R_COMMENT	VARCHAR(152)
) USING VIDEX;`
2. use function videx_analyze to copy statistics
`SELECT videx_analyze('REGION'::regclass, 'V_REGION'::regclass)"`
3. explain sql