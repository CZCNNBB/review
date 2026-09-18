"""应用启动前需要执行的基础环境初始化。"""

import os
import asyncio
from dotenv import load_dotenv

# Windows 环境需要在其他异步组件导入前切换事件循环策略。
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 本地 .env 仅补充缺失配置，不覆盖容器或部署平台注入的环境变量。
load_dotenv(override=False)
