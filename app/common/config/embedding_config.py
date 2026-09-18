# 初始化 PGVector 客户端
import os
from langchain_ollama import OllamaEmbeddings

# 初始化 Ollama Embeddings
ollama_embeddings = OllamaEmbeddings(
    model=os.getenv("OLLAMA_EMBEDDING_MODEL"),
    base_url=os.getenv("OLLAMA_BASE_URL"),  # ollama地址
)


