# -------------------数据库连接------------------------
# 该模块负责数据库连接，包括连接池的创建、连接的获取和释放等。

from sqlmodel import create_engine, inspect, text

class MysqlDatabase:
   """
   数据库连接
   """
   def __init__(self, connection_string: str):
      """
      初始化数据库连接

     Args:
         connection_string (str): 数据库连接字符串,格式为"mysql+pymysql://user:password@host:port/database"
      """
      # 使用create_engine创建数据库引擎
      self.engine = create_engine(
      connection_string, 
      pool_size=20,           # 连接池大小，20
      max_overflow=30,        # 连接池最大溢出数，30
      pool_timeout=30,        # 连接池等待连接的最长时间，30秒
      pool_recycle=3600,      # 连接池回收时间，1小时
      pool_pre_ping=True,     # 连接使用前检查有效性
      )  

   def get_table_name(self):
      """
      获取数据库表名

      Returns:
          list: 数据库表名列表
      """
      try:
         # 通过inspect创建一个数据库映射对象，通过self.engine拿到了数据库引擎
         inspector = inspect(self.engine)
         return inspector.get_table_names()
      except Exception as e:
         raise Exception(f"获取数据库表名失败: {e}")
      
   def get_table_Information(self, table_name: str):
      """
      获取数据库表信息

      Args:
          table_name (str): 表名

      Returns:
          list: 数据库表信息列表
      """
      try:
         inspector = inspect(self.engine)
         return inspector.get_columns(table_name)
      except Exception as e:
         raise Exception(f"获取数据库表信息失败: {e}")
         
   def execute_query(self, query: str):
      """
      执行SQL查询

      Args:
          query (str): SQL查询语句

      Returns:
          list: 查询结果列表
      """
      # 安全检查
      forbidden_keywords = ["create", "insert", "update", "delete", "drop", "truncate","grant"]
      query_lower = query.lower().strip()
      # 检查查询是否包含危险操作
      if not query_lower.startswith(("select", "with")) and any(
         keywords in query_lower for keywords in forbidden_keywords):
         raise Exception("出于安全考虑,只允许执行SELECT查询和with查询")
      
      # 执行Sql语句进行查询
      try:
         with self.engine.connect() as connection:
            result = connection.execute(text(query))

            # 获取列名
            columns = result.keys()

            # 防止内存溢出，每次只获取100条数据
            rows = result.fetchmany(100)

            if not rows:
               return {"查询结果为空"}

            return {"columns": columns, "rows": rows}
      except Exception as e:
         raise Exception(f"执行SQL查询失败: {e}")
      
   def validate_query(self, query: str):
      """
      验证SQL查询语句是否正确

      Args:
            query (str): SQL查询语句
      """
      # 基本语法检查
      if not query or not query.strip():
         return "错误:sql语句不能为空"

      # 检查是否以SELECT或WITH开头
      query_lower = query.lower().strip()
      if not query_lower.startswith(("select", "with")):
         return "警告:建议以SELECT或WITH开头,否则可能被限制"
      
      try:
         with self.engine.connect() as connection:
            # 使用SQLAlchemy的text()方法解析SQL语句，但不执行
            parsed_query = text(query)         
            # 尝试编译查询语句，检查是否有语法错误
            compiled = parsed_query.compile(compile_kwargs={"literal_binds": True})
            return "SQL查询语句语法正确"
      except Exception as e:
         return f"查询语句语法错误: {e}"
    



if __name__ == "__main__":
    # 测试数据库连接
    DB_CONFIG = {
    "host": "192.168.8.19",
    "port": 3306,
    "username": "root",
    "password": "CZC96995",
    "database": "tenderinformation",
}
    connection_string = f"mysql+pymysql://{DB_CONFIG['username']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    manager = MysqlDatabase(connection_string)
    print(manager.get_table_name())
    print(manager.get_table_Information("users"))
    print(manager.validate_query("select * from users"))
    print(manager.execute_query("select * from users"))
