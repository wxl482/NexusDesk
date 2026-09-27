import os
from typing import Optional, Dict, Any
# 引入 LangChain 核心模型与嵌入协议
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.embeddings import Embeddings
from langchain_core.messages import HumanMessage
from app.core.config import settings

class LLMFactory:
    """
    统一大语言模型与向量嵌入工厂类（LangChain Model & Embeddings Factory）。
    支持所有符合 OpenAI 接口规范的 LLM 供应商：
    - DeepSeek（deepseek-chat 对话模型，deepseek-reasoner 深度思考R1模型）
    - OpenAI（gpt-4o, gpt-4o-mini 等）
    - Ollama 本地私有化模型（如 base_url="http://localhost:11434/v1", model="llama3.2"）
    - 智谱 GLM、通义千问 Qwen、月之暗面 Kimi 等兼容接口
    """

    @classmethod
    def get_chat_model(
        cls,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: Optional[float] = None,
        streaming: bool = True,
        extra_kwargs: Optional[Dict[str, Any]] = None,
    ) -> ChatOpenAI:
        """
        获取配置好的 LangChain 聊天模型实例 (ChatOpenAI)。

        参数:
            model: 模型名称标识（如 deepseek-chat 或 gpt-4o）
            base_url: API 访问基础路径
            api_key: 访问凭据密钥
            temperature: 采样温度（0.0 代表严谨确定，1.0+ 代表创意发散）
            streaming: 是否开启流式 Token 生成
            extra_kwargs: 传递给底层客户端的额外配置参数

        返回:
            ChatOpenAI: 配置就绪的 LangChain 聊天客户端
        """
        model_name = model or settings.DEFAULT_MODEL
        target_base_url = base_url or settings.DEFAULT_BASE_URL
        target_api_key = api_key or settings.DEFAULT_API_KEY
        target_temp = temperature if temperature is not None else settings.DEFAULT_TEMPERATURE

        # 当使用本地或免密接口时，确保 api_key 非空，避免底层 OpenAI 客户端报错
        if not target_api_key:
            target_api_key = "dummy-key-for-local-endpoint"

        kwargs: Dict[str, Any] = {
            "model": model_name,
            "api_key": target_api_key,
            "base_url": target_base_url,
            "temperature": target_temp,
            "streaming": streaming,
            "timeout": 60,
        }

        if extra_kwargs:
            kwargs.update(extra_kwargs)

        return ChatOpenAI(**kwargs)

    @classmethod
    def get_embeddings(
        cls,
        model: str = "text-embedding-3-small",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> Embeddings:
        """
        获取 LangChain 标准 Embeddings 嵌入对象。
        若传入有效远程 Key，则使用 LangChain OpenAIEmbeddings；否则回退为本地离线嵌入。
        """
        target_api_key = api_key or settings.DEFAULT_API_KEY
        target_base_url = base_url or settings.DEFAULT_BASE_URL

        if target_api_key and target_api_key != "dummy-key-for-local-endpoint":
            return OpenAIEmbeddings(
                model=model,
                api_key=target_api_key,
                base_url=target_base_url,
            )
        from app.rag.vector_engine import LocalChromadbEmbeddings
        return LocalChromadbEmbeddings()

    @classmethod
    async def test_connection(
        cls,
        model: str,
        base_url: str,
        api_key: str,
    ) -> Dict[str, Any]:
        """
        在线测试大模型连通性与配置可用性。

        参数:
            model: 待测试的模型标识
            base_url: 接口地址
            api_key: 密钥凭据

        返回:
            Dict: 包含测试状态 success、响应内容 reply 或错误信息 error
        """
        try:
            llm = cls.get_chat_model(
                model=model,
                base_url=base_url,
                api_key=api_key,
                temperature=0.1,
                streaming=False,
            )
            # 发送最简 ping 请求以验证端到端鉴权与通信
            response = await llm.ainvoke([HumanMessage(content="你好！请仅回复 'OK'。")])
            return {
                "success": True,
                "message": "模型服务连接测试成功",
                "reply": response.content,
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    @classmethod
    async def fetch_models(
        cls,
        base_url: str,
        api_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        实时从服务商接口拉取所有当前可用的模型清单。
        兼容标准 OpenAI 协议（GET /models）及本地 Ollama 协议（/v1/models 或 /api/tags）。
        """
        import os
        import httpx

        # 修复 macOS/Linux 下 IPv6 (::1) 在 NO_PROXY 中导致的 httpx.InvalidURL 缺陷
        for _k in ["NO_PROXY", "no_proxy"]:
            _v = os.environ.get(_k)
            if _v and "::" in _v:
                os.environ[_k] = ",".join([p.strip() for p in _v.split(",") if not p.strip().startswith("::")])

        target_base_url = (base_url or settings.DEFAULT_BASE_URL).rstrip("/")
        target_api_key = api_key or settings.DEFAULT_API_KEY

        # 构造优先尝试的候选端点（自适应处理是否带 /v1 后缀）
        candidate_urls = [f"{target_base_url}/models"]
        if target_base_url.endswith("/v1"):
            root_url = target_base_url[:-3].rstrip("/")
            candidate_urls.append(f"{root_url}/models")
        else:
            candidate_urls.append(f"{target_base_url}/v1/models")
        candidate_urls.append(f"{target_base_url}/api/tags")

        headers = {}
        if target_api_key and target_api_key != "dummy-key-for-local-endpoint":
            headers["Authorization"] = f"Bearer {target_api_key}"

        def _create_client():
            try:
                return httpx.AsyncClient(timeout=15.0)
            except Exception:
                return httpx.AsyncClient(timeout=15.0, trust_env=False)

        last_error = ""
        try:
            async with _create_client() as client:
                for url in candidate_urls:
                    try:
                        resp = await client.get(url, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            raw_models = []
                            # 格式 1：OpenAI 标准 { "data": [ {"id": "..."} ] }
                            if "data" in data and isinstance(data["data"], list):
                                raw_models = data["data"]
                            # 格式 2：Ollama 原生 { "models": [ {"name": "..."} ] }
                            elif "models" in data and isinstance(data["models"], list):
                                raw_models = data["models"]

                            model_list = []
                            seen_ids = set()
                            for item in raw_models:
                                m_id = None
                                owned_by = ""
                                if isinstance(item, dict):
                                    m_id = item.get("id") or item.get("name") or item.get("model")
                                    owned_by = item.get("owned_by", "")
                                elif isinstance(item, str):
                                    m_id = item

                                if m_id and str(m_id) not in seen_ids:
                                    seen_ids.add(str(m_id))
                                    model_list.append({
                                        "id": str(m_id),
                                        "name": str(m_id),
                                        "owned_by": str(owned_by) if owned_by else "",
                                    })

                            # 按名称字母顺序排序
                            model_list.sort(key=lambda x: x["id"].lower())

                            if model_list:
                                return {
                                    "success": True,
                                    "models": model_list,
                                    "total": len(model_list),
                                    "source_url": url,
                                }
                        elif resp.status_code in (401, 403):
                            try:
                                err_json = resp.json()
                                err_msg = err_json.get("error", {}).get("message") or resp.text
                            except Exception:
                                err_msg = resp.text
                            return {
                                "success": False,
                                "error": f"服务商认证失败 (状态码 {resp.status_code})：{err_msg}。请检查 API Key 是否有效。",
                            }
                        else:
                            last_error = f"服务商接口返回状态码 {resp.status_code}"
                    except httpx.ConnectError:
                        last_error = f"无法连接到服务地址 {target_base_url}，请确认服务已启动或网络通畅。"
                    except httpx.TimeoutException:
                        last_error = f"拉取超时：请求 {target_base_url} 超过 15 秒未响应。"
                    except Exception as e:
                        last_error = str(e)
        except Exception as outer_e:
            last_error = f"网络请求异常: {str(outer_e)}"

        return {
            "success": False,
            "error": last_error or "未获取到模型列表，请检查 Base URL 与 API Key 是否有效。",
        }

