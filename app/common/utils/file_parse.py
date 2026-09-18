
import base64
import httpx
import requests
from langchain_community.document_loaders import PyPDFLoader, UnstructuredFileLoader
from app.common.config.plugins_config import MinerU_API_URL
import asyncio

# --------------------同步--------------------

# PDF解析
class PdfParse:
    @staticmethod
    def get_miner(file):
        """
        通过 MinerU 解析 PDF，返回 Markdown 文本
        """
        miner_url = MinerU_API_URL
        headers={
            "accept" : "application/json",
            "Content-Type" : "multipart/form-data;boundary=----WebKitFormBoundaryprlezsleeudzctfx"
        }
        try:
            # 准备 multipart/form-data 数据
            files = {
                'file': (file.filename, file.file, 'application/pdf')  # file 参数
            }
            
            data = {
                'return_md': "true"  # return_md 参数
            }
            
            resp = requests.post(
                miner_url,
                headers=headers,
                files=files,
                data=data,
                timeout=600  # 设置超时时间
            )
            
            # 检查响应状态
            resp.raise_for_status()
            
            return resp.text
        except Exception as e:
            return f"解析文件失败: {str(e)}"
    
    @staticmethod
    def parse_pdf_PyPDFLoader(temp_path):
        """
        通过 PyPDFLoader 解析 PDF，返回 Document 列表

        Args:
            temp_path (str): 临时文件路径
        Returns:
            list: 解析后的 Document 列表
        """
        # 3. 使用 PyPDFLoader 解析
        loader = PyPDFLoader(temp_path)
        docs = loader.load()
        full_text = "\n\n".join([doc.page_content for doc in docs])
        return full_text

# Word解析
class DocxParse:
    @staticmethod
    def parse_docx_UnstructuredFileLoader(temp_path):
        loader = UnstructuredFileLoader(temp_path)
        docs = loader.load()
        full_text = "\n\n".join([doc.page_content for doc in docs])
        return full_text
    
# 文本解析
class TextParse:
    @staticmethod
    def parse_txt_UnstructuredFileLoader(temp_path):
        loader = UnstructuredFileLoader(temp_path)
        docs = loader.load()
        full_text = "\n\n".join([doc.page_content for doc in docs])
        return full_text
    
# 图片解析
class ImageParse:
    @staticmethod
    def parse_image_UnstructuredFileLoader(temp_path):
        with open(temp_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
        

# -------------------------------异步---------------------------

# PDF解析
class PdfParse_Async:
    @staticmethod
    async def get_miner(file):
        """
        通过 MinerU 解析 PDF，返回 Markdown 文本
        """
        miner_url = MinerU_API_URL
        headers={
            "accept" : "application/json",
            "Content-Type" : "multipart/form-data;boundary=----WebKitFormBoundaryprlezsleeudzctfx"
        }
        try:
            # 准备 multipart/form-data 数据
            files = {
                'file': (file.filename, file.file, 'application/pdf')  # file 参数
            }
            
            data = {
                'return_md': "true"  # return_md 参数
            }
            
           # 通过httpx库的异步POST请求
            async with httpx.AsyncClient(timeout=600) as client:
                response = await client.post(miner_url, headers=headers, files=files, data=data)
                response.raise_for_status()
                return response.text
        except Exception as e:
            return f"解析文件失败: {str(e)}"
    
    @staticmethod
    async def parse_pdf_PyPDFLoader(temp_path):
        """
        通过 PyPDFLoader 解析 PDF，返回 Document 列表

        Args:
            temp_path (str): 临时文件路径
        Returns:
            list: 解析后的 Document 列表
        """
        # 3. 使用 PyPDFLoader 解析
        loader = PyPDFLoader(temp_path)
        docs = await loader.aload()
        full_text = "\n\n".join([doc.page_content for doc in docs])
        return full_text



# Word解析
class DocxParse_Async:
    @staticmethod
    async def parse_docx_UnstructuredFileLoader(temp_path):
        loader = UnstructuredFileLoader(temp_path)
        docs = await loader.aload()
        full_text = "\n\n".join([doc.page_content for doc in docs])
        return full_text
    
# 文本解析
class TextParse_Async:
    @staticmethod
    async def parse_txt_UnstructuredFileLoader(temp_path):
        loader = UnstructuredFileLoader(temp_path)
        docs = await loader.aload()
        full_text = "\n\n".join([doc.page_content for doc in docs])
        return full_text
    
# 图片解析为base64字符串
class ImageParse_Async:
    @staticmethod
    async def parse_image_UnstructuredFileLoader(temp_path):
        def _read_and_b64(path: str) -> str:
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")

        return await asyncio.to_thread(_read_and_b64, temp_path)
