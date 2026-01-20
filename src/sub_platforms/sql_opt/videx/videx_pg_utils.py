import logging
import urllib.parse
from typing import Optional
import subprocess
import os

from sqlalchemy import create_engine
import psycopg2

from sub_platforms.sql_opt.videx.videx_mysql_utils import AbstractMySQLUtils
from sub_platforms.sql_opt.videx.videx_mysql_utils import BaseDBConnectionConfig
from sub_platforms.sql_opt.videx.videx_mysql_utils import DBTYPE

class PGConnectionConfig(BaseDBConnectionConfig):
    port: Optional[int] = 5432

def get_pg_utils(config: PGConnectionConfig):
    if config.dbtype == DBTYPE.POSTGRESQL:
        return OpenPGUtils(config)
    else:
        raise Exception('not support datasource')

class OpenPGUtils(AbstractMySQLUtils):
    """
    Open-source PostgreSQL connection class, used to connect with host, port, user and password.
    """

    def __init__(self, config: PGConnectionConfig):
        super().__init__('open_pg', config.schema, config.charset,
                         config.read_timeout, config.write_timeout, config.connect_timeout)
        self.host = config.host
        self.port = config.port
        self.user = config.user
        self.password = config.pwd
        

    def get_connection(self):
        conn = psycopg2.connect(
            user=self.user,
            password=self.password,
            dbname=self.database,
            host=self.host,
            port=self.port,
            connect_timeout=self.connect_timeout,
            options=f'-c client_encoding={self.charset or "utf8"}'
        )
        conn.autocommit = True
        return conn

    def get_sqlalchemy_engine(self, dbname: str = None):
        dbname = dbname if dbname is not None else self.database
        return create_engine(
            "postgresql+psycopg2://{user}:{pw}@{host}:{port}/{db}".format(
                host=self.host,
                port=self.port,
                db=dbname,
                user=self.user,
                pw=urllib.parse.quote_plus(self.password)
            )
        )

    def __repr__(self):
        return f"OpenPG:{self.host}:{self.port}/{self.database}"

    def __str__(self):
        return self.__repr__()
    
    def execute_query(self, sql: str, params: list = None):
        if self.pool is None:
            self.pool = self.get_shared_pool()
        with self.pool.connection() as c:
            with c.cursor() as cursor:
                cursor.execute(sql, params)
                if cursor.rowcount > 0:
                    return cursor.fetchall()
                else:
                    return None
    def get_user(self):
        return self.user
    
    def pg_dump(self, db_name, schema_name, table_name) -> str:
        env = os.environ.copy()
        env["PGPASSWORD"] = self.password

        cmd = [
            "pg_dump",
            "-U", self.user,
            "--schema-only",
            "--no-owner",
            "--no-privileges",
            "--no-comments",
            "-d", db_name,
            "-n", schema_name,
            "-t", table_name,
            "-p", str(self.port),
            "-h", self.host,
        ]
        try:
            result = subprocess.run(cmd, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, text=True)
            sql_text = result.stdout
            return sql_text
        except subprocess.CalledProcessError as e:
                logging.error(f"pg_dump error:, {e.stderr}")
                raise e