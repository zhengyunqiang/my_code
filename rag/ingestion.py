import os
import re
import hashlib
import logging
from typing import List, Optional, Dict, Any
from pathlib import Path

# LangChain imports
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import (
    PyPDFLoader,
    TextLoader,
    UnstructuredMarkdownLoader,
    Docx2txtLoader
)

# --- 配置日志 ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


class DocumentProcessor:
    def __init__(
            self,
            chunk_size: int = 800,
            chunk_overlap: int = 100,
            min_length: int = 50
    ):
        """
        初始化文档处理器
        :param chunk_size: 切分块大小
        :param chunk_overlap: 切分重叠大小
        :param min_length: 丢弃过短的文本块（例如只有页码或标题的噪音）
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_length = min_length

        # 针对中文优化的分隔符
        # 优先级：段落(\n\n) -> 句子(。！？) -> 单词(空格)
        self.text_splitter = RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", "。", "！", "？", "；", " ", ""],
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            is_separator_regex=False
        )

    def clean_text(self, text: str) -> str:
        """
        生产级清洗逻辑：修复常见的 PDF 解析问题
        """
        if not text:
            return ""

        # 1. 修复连字符断词 (例如: "commu-\nnication" -> "communication")
        text = re.sub(r'(\w+)-\n(\w+)', r'\1\2', text)

        # 2. 去除多余的换行符 (PDF经常把一句话切成多行)
        # 策略：如果换行符前后都是非空字符，大概率是断行，替换为空格
        text = re.sub(r'(?<!\n)\n(?!\n)', ' ', text)

        # 3. 归一化连续空格
        text = re.sub(r'\s+', ' ', text)

        # 4. 去除不可见字符（保留基础标点）
        text = re.sub(r'[^\w\s\u4e00-\u9fa5,.\?!;:"\'\(\)\[\]]', '', text)

        return text.strip()

    def generate_content_hash(self, content: str) -> str:
        """生成内容指纹，用于后续数据库去重"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _get_loader(self, file_path: Path):
        """根据文件扩展名选择合适的 Loader"""
        ext = file_path.suffix.lower()
        if ext == ".pdf":
            return PyPDFLoader(str(file_path))
        elif ext == ".txt":
            return TextLoader(str(file_path), encoding="utf-8")
        elif ext in [".md", ".markdown"]:
            return UnstructuredMarkdownLoader(str(file_path))
        elif ext in [".docx", ".doc"]:
            return Docx2txtLoader(str(file_path))
        else:
            raise ValueError(f"不支持的文件格式: {ext}")

    def process_file(self, file_path: str) -> List[Document]:
        """
        处理单个文件：加载 -> 清洗 -> 切分 -> 增强元数据
        """
        path_obj = Path(file_path)
        if not path_obj.exists():
            logger.error(f"文件不存在: {file_path}")
            return []

        chunks = []
        try:
            logger.info(f"开始处理文件: {path_obj.name}")

            # 1. 加载
            loader = self._get_loader(path_obj)
            raw_docs = loader.load()

            # 2. 清洗与元数据增强 (在切分前做)
            cleaned_docs = []
            for doc in raw_docs:
                cleaned_content = self.clean_text(doc.page_content)
                # 过滤掉内容太少的页（如空白页或只有页眉的页）
                if len(cleaned_content) < self.min_length:
                    continue

                doc.page_content = cleaned_content
                # 统一元数据字段
                doc.metadata["source"] = str(path_obj)
                doc.metadata["filename"] = path_obj.name
                doc.metadata["extension"] = path_obj.suffix
                cleaned_docs.append(doc)

            if not cleaned_docs:
                logger.warning(f"文件内容为空或已被过滤: {path_obj.name}")
                return []

            # 3. 切分
            chunks = self.text_splitter.split_documents(cleaned_docs)

            # 4. 为每个 Chunk 添加唯一 ID (用于幂等性写入)
            for i, chunk in enumerate(chunks):
                # ID 规则：文件Hash + 块序号 (或者使用内容Hash)
                content_hash = self.generate_content_hash(chunk.page_content)
                chunk.metadata["chunk_id"] = f"{path_obj.stem}_{i}"
                chunk.metadata["content_hash"] = content_hash
                chunk.metadata["chunk_index"] = i

            logger.info(f"成功处理: {path_obj.name}, 生成 {len(chunks)} 个片段")

        except Exception as e:
            logger.error(f"处理文件失败 {file_path}: {str(e)}", exc_info=True)

        return chunks

    def process_directory(self, dir_path: str) -> List[Document]:
        """批量处理目录下所有支持的文件"""
        all_chunks = []
        directory = Path(dir_path)

        if not directory.exists():
            logger.error(f"目录不存在: {dir_path}")
            return []

        # 遍历目录
        supported_extensions = {".pdf", ".txt", ".md", ".docx"}
        files = [
            f for f in directory.rglob("*")
            if f.suffix.lower() in supported_extensions and f.is_file()
        ]

        logger.info(f"在目录中发现 {len(files)} 个支持的文件")

        for file_path in files:
            file_chunks = self.process_file(str(file_path))
            all_chunks.extend(file_chunks)

        logger.info(f"处理完成。总计生成 {len(all_chunks)} 个片段")
        return all_chunks


# --- 使用示例 ---
if __name__ == "__main__":
    # 假设你有一个 'data' 文件夹，里面放着 PDF 和 txt
    processor = DocumentProcessor(chunk_size=500, chunk_overlap=50)

    # 执行处理
    documents = processor.process_directory("./data")

    # 打印前两个结果看看效果
    if documents:
        print("\n--- 示例片段 1 ---")
        print(f"内容: {documents[0].page_content[:100]}...")
        print(f"元数据: {documents[0].metadata}")

        print("\n--- 示例片段 2 ---")
        print(f"内容: {documents[2].page_content[:100]}...")
        print(f"元数据: {documents[2].metadata}")

        print("\n--- 示例片段 3 ---")
        print(f"内容: {documents[3].page_content[:100]}...")
        print(f"元数据: {documents[3].metadata}")

        print("\n--- 示例片段 4 ---")
        print(f"内容: {documents[1].page_content[:100]}...")
        print(f"元数据: {documents[1].metadata}")