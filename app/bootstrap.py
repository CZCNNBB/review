"""应用启动前需要执行的基础环境初始化。"""

import os
import asyncio
import logging
from dotenv import load_dotenv

# Windows 环境需要在其他异步组件导入前切换事件循环策略。
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# 本地 .env 仅补充缺失配置，不覆盖容器或部署平台注入的环境变量。
load_dotenv(override=False)


def configure_logging(level: int = logging.INFO) -> None:
    """给应用自己的日志装上输出。

    uvicorn 只配置它自己的 logger，应用模块的日志没有处理器：INFO 会被静默丢掉，
    WARNING 以上才由 logging 的兜底处理器打到 stderr（只有一行消息，没有级别和来源）。
    启动时配置一次，节点定义同步、业务执行 Worker 这些启动日志才看得见。

    只在启动应用时调用；测试与脚本不调用，保持它们原有的静默行为。
    """

    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s")
