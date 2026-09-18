# windows环境设置
import os
import asyncio
from dotenv import load_dotenv

# 1. 在「任何 import 」之前就换策略
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 2. 加载环境变量
load_dotenv(override=True)  # 加载同目录下的.env文件中的环境变量，存入os.environ中