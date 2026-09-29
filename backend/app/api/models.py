from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field
from app.core.config import settings
from app.llm.factory import LLMFactory

router = APIRouter(prefix="/api/models", tags=["模型配置与连通性"])

class ModelTestRequest(BaseModel):
    """大模型连通性测试入参 Schema"""
    model: str = Field(..., description="模型标识，如 deepseek-chat 或 gpt-4o")
    base_url: str = Field(..., description="API 基础路径")
    api_key: str = Field(..., description="访问密钥凭据")

DEFAULT_PROVIDERS = [
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "baseUrl": "https://api.deepseek.com/v1",
        "defaultModel": "deepseek-chat",
        "keyUrl": "https://platform.deepseek.com/api_keys",
        "needKey": True,
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "baseUrl": "https://api.openai.com/v1",
        "defaultModel": "gpt-4o-mini",
        "keyUrl": "https://platform.openai.com/api-keys",
        "needKey": True,
    },
    {
        "id": "qwen",
        "name": "通义千问 (Qwen)",
        "baseUrl": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "defaultModel": "qwen-plus",
        "keyUrl": "https://dashscope.console.aliyun.com/apiKey",
        "needKey": True,
    },
    {
        "id": "moonshot",
        "name": "月之暗面 (Kimi)",
        "baseUrl": "https://api.moonshot.cn/v1",
        "defaultModel": "moonshot-v1-8k",
        "keyUrl": "https://platform.moonshot.cn/console/api-keys",
        "needKey": True,
    },
    {
        "id": "zhipu",
        "name": "智谱清言 (GLM)",
        "baseUrl": "https://open.bigmodel.cn/api/paas/v4",
        "defaultModel": "glm-4-flash",
        "keyUrl": "https://bigmodel.cn/usercenter/apikeys",
        "needKey": True,
    },
    {
        "id": "ollama",
        "name": "Ollama (本地部署)",
        "baseUrl": "http://localhost:11434/v1",
        "defaultModel": "llama3.2",
        "keyUrl": None,
        "needKey": False,
    },
    {
        "id": "custom",
        "name": "自定义网关",
        "baseUrl": "https://api.openai.com/v1",
        "defaultModel": "gpt-4o-mini",
        "keyUrl": None,
        "needKey": True,
    },
]

@router.get("/providers")
async def get_providers():
    """
    获取服务端统一维护的主流大模型服务商标准配置列表（无硬编码 Tag，方便随时平滑增删厂商）。
    """
    return {"providers": DEFAULT_PROVIDERS}

@router.get("/config")
async def get_model_config():
    """
    获取后端默认模型配置以及常见商用/开源大模型的快捷配置预设。
    """
    return {
        "default_model": settings.DEFAULT_MODEL,
        "default_base_url": settings.DEFAULT_BASE_URL,
        "default_api_key_set": bool(settings.DEFAULT_API_KEY),
        "default_temperature": settings.DEFAULT_TEMPERATURE,
        "providers": DEFAULT_PROVIDERS,
    }

@router.post("/test")
async def test_model(req: ModelTestRequest):
    """
    在线测试指定的大模型接口凭据连通性与服务响应速度。
    """
    result = await LLMFactory.test_connection(
        model=req.model,
        base_url=req.base_url,
        api_key=req.api_key,
    )
    return result

class ModelFetchRequest(BaseModel):
    """拉取最新模型列表入参 Schema"""
    base_url: str = Field(..., description="API 基础路径")
    api_key: Optional[str] = Field(None, description="访问密钥凭据（本地如 Ollama 可选）")

@router.post("/fetch")
async def fetch_models(req: ModelFetchRequest):
    """
    实时从目标大模型服务商接口拉取所有当前最新可用的模型列表。
    """
    try:
        result = await LLMFactory.fetch_models(
            base_url=req.base_url,
            api_key=req.api_key,
        )
        return result
    except Exception as e:
        return {
            "success": False,
            "error": f"拉取模型列表失败: {str(e)}",
            "models": [],
        }


class ModelRouteRequest(BaseModel):
    """模型路由请求 Schema"""
    prompt: str = Field(..., description="用户输入的提问文本或提示词")
    current_model: Optional[str] = Field(default=None, description="当前已选模型")


@router.post("/route")
async def route_model(req: ModelRouteRequest):
    """
    【智能动态模型路由】分析提示词意图特征，自动匹配最适合的极速 (Fast) 或深度推理 (Reasoning) 模型
    """
    from app.llm.router import ModelRouter
    decision = ModelRouter.route_prompt(req.prompt, req.current_model)
    return {"success": True, "decision": decision}

