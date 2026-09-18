
# ------------------------关系型数据库-------------------------
# 配置Mysql数据库连接
import os

from elasticsearch import Elasticsearch
Mysql_CONFIG = {
    "host": os.getenv("MYSQL_HOST"),
    "port": int(os.getenv("MYSQL_PORT")),
    "username": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
}

# 数据库连接字符串
connection_string = f"mysql+pymysql://{Mysql_CONFIG['username']}:{Mysql_CONFIG['password']}@{Mysql_CONFIG['host']}:{Mysql_CONFIG['port']}/{Mysql_CONFIG['database']}"

# 配置Postgres数据库连接
postgres_db_CONFIG = {
    "host": os.getenv("POSTGRES_HOST"),
    "port": int(os.getenv("POSTGRES_PORT")),
    "username": os.getenv("POSTGRES_USER"),
    "password": os.getenv("POSTGRES_PASSWORD"),
    "database": os.getenv("POSTGRES_DATABASE"),
}
# 数据库连接字符串
postgres_connection_string = f"postgresql://{postgres_db_CONFIG['username']}:{postgres_db_CONFIG['password']}@{postgres_db_CONFIG['host']}:{postgres_db_CONFIG['port']}/{postgres_db_CONFIG['database']}"


# ------------------------向量数据库-------------------------

# 配置向量数据库PGvector数据库连接
PGvector_db_CONFIG = {
    "host": os.getenv("PGVECTOR_HOST"),
    "port": int(os.getenv("PGVECTOR_PORT")),
    "username": os.getenv("PGVECTOR_USER"),
    "password": os.getenv("PGVECTOR_PASSWORD"),
    "database": os.getenv("PGVECTOR_DATABASE"),
}
PGvector_connection_string =f"postgresql+psycopg://{PGvector_db_CONFIG['username']}:{PGvector_db_CONFIG['password']}@{PGvector_db_CONFIG['host']}:{PGvector_db_CONFIG['port']}/{PGvector_db_CONFIG['database']}"


# 配置Elasticsearch数据库连接
es_client = Elasticsearch(
    hosts=[os.getenv("ES_HOST")]  # es主机地址
)
ES_HOST = os.getenv("ES_HOST")
ES_VERSION = os.getenv("ES_VERSION")