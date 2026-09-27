import os
from pathlib import Path
from pydantic_settings import BaseSettings

# 项目基础路径与数据持久化目录定义
BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
VECTOR_STORE_DIR = DATA_DIR / "chroma"
MILVUS_DIR = DATA_DIR / "milvus"
BACKUP_DIR = DATA_DIR / "backups"
USER_BACKUP_DIR = Path.home() / ".nexusdesk" / "backups"
WORKSPACE_DIR = DATA_DIR / "workspace"
LOG_DIR = BASE_DIR / "logs"

# 自动确保数据目录及子目录存在
DATA_DIR.mkdir(parents=True, exist_ok=True)
VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
MILVUS_DIR.mkdir(parents=True, exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
USER_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """
    系统全局配置类，基于 Pydantic BaseSettings 实现。
    支持自动读取环境变量与本地 .env 配置文件。
    """
    # 基础应用配置
    APP_NAME: str = "NexusDesk"
    VERSION: str = "1.0.0"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = True

    # 默认大语言模型配置（基于统一的 OpenAI 兼容协议）
    DEFAULT_PROVIDER: str = "openai_compatible"
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "deepseek-chat")
    DEFAULT_BASE_URL: str = os.getenv("DEFAULT_BASE_URL", "https://api.deepseek.com/v1")
    DEFAULT_API_KEY: str = os.getenv("DEFAULT_API_KEY", "")
    DEFAULT_TEMPERATURE: float = 0.7

    # 1. 智谱 AI 嵌入配置
    ZHIPUAI_API_KEY: str = os.getenv("ZHIPUAI_API_KEY", "")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "embedding-3")

    # 2. Milvus 向量数据库与安全灾备配置（方案 C：本地轻量级 + 自动双写备份快照）
    MILVUS_PATH: Path = MILVUS_DIR / "nexusdesk.db"
    MILVUS_URI: str = os.getenv("MILVUS_URI", str(MILVUS_DIR / "nexusdesk.db"))
    MILVUS_TOKEN: str = os.getenv("MILVUS_TOKEN", "")
    BACKUP_PATH: Path = BACKUP_DIR
    USER_BACKUP_PATH: Path = USER_BACKUP_DIR

    # 数据与存储路径
    DATA_PATH: Path = DATA_DIR
    CHROMA_PATH: Path = VECTOR_STORE_DIR
    WORKSPACE_PATH: Path = WORKSPACE_DIR
    DB_PATH: Path = DATA_DIR / "agent_sessions.db"
    LOG_PATH: Path = LOG_DIR

    # 日志记录配置
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_ROTATION: str = os.getenv("LOG_ROTATION", "00:00")
    LOG_RETENTION: str = os.getenv("LOG_RETENTION", "10 days")

    # 检索与外部工具密钥配置
    TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "")

    class Config:
        """Pydantic 配置项"""
        env_file = ".env"
        extra = "allow"


# 导出全局单例配置对象
settings = Settings()
