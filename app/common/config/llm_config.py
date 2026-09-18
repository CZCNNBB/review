# -------------------配置文件------------------------
# 该模块负责配置langchain模块，包括模型参数、服务器地址等。

import os
from langchain_deepseek import ChatDeepSeek
from langchain_ollama import ChatOllama
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_openai import ChatOpenAI

from dotenv import load_dotenv

load_dotenv(override=True)

# 速率限制，防止模型被过度调用(一般不使用,会严重影响用户体验)
rate_limiter = InMemoryRateLimiter(
    requests_per_second=10, # 每秒最多10个请求
    check_every_n_seconds=1, # 每1秒检查一次速率限制
    max_bucket_size=20, # 最大的并发请求数
    # 其他参数
)


# 通过langchain_ollama配置远程 Ollama 服务器上的模型
model_qwen3 = ChatOllama(
    model=os.getenv("OLLAMA_LLM_MODEL"),
    base_url=os.getenv("OLLAMA_BASE_URL"),  # ollama地址
    temperature=0.5,  # 温度参数，控制模型输出的随机性，默认值为0.5
    top_p=0.9,  # 控制模型输出的多样性，默认值为0.9
    max_tokens=1024,  # 最大输出 token 数，默认值为1024 
    # 往下可以添加其他参数
)

model_qwenVL = ChatOllama(
    model=os.getenv("OLLAMA_VL_MODEL"),
    base_url=os.getenv("OLLAMA_BASE_URL"),  # ollama地址
    temperature=0.5,  # 温度参数，控制模型输出的随机性，默认值为0.5
    top_p=0.9,  # 控制模型输出的多样性，默认值为0.9
    max_tokens=1024,  # 最大输出 token 数，默认值为1024 
)

# 调用Deepseek模型，通过服务
Deepseek_model = ChatDeepSeek(
    model = os.getenv("DEEPSEEK_MODEL"),
    temperature = 0.5,
    api_key = os.getenv("Deepseek_API_Key"),
    base_url=os.getenv("Deepseek_URL")
)

# 调用火山引擎模型，通过服务
DouBao_model = ChatOpenAI(
    model=os.getenv("Huoshan_LLM_MODEL"),
    api_key=os.getenv("Huoshan_API_Key"),
    base_url=os.getenv("Huoshan_URL"),
    temperature=0.7,    # 温度参数，控制模型输出的随机性，默认值为0.7
    max_tokens=8196,    # 最大输出 token 数，默认值为2048
)

    
# api_key=os.getenv("Huoshan_API_Key"),   # 从环境变量中获取Huoshan_API_Key
#     base_url=os.getenv("Huoshan_URL"),  # 从环境变量中获取Huoshan_URL
