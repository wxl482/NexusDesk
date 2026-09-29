import time
import logging
from collections import OrderedDict
from typing import List, Dict, Any, Optional
import requests
from lxml import html
from langchain_core.tools import tool
from app.core.config import settings

logger = logging.getLogger(__name__)

# 内存近实时搜索缓存：最多保留 100 条最近查询，有效期 15 分钟 (900秒)
_SEARCH_CACHE: OrderedDict[str, tuple[float, str]] = OrderedDict()
_CACHE_MAX_SIZE = 100
_CACHE_TTL = 900  # 秒

_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
]


def _search_tavily(query: str, max_results: int = 5, timeout: float = 6.0) -> tuple[Optional[str], List[Dict[str, str]]]:
    """
    第一优先级：Tavily 官方专为 AI Agent 优化的搜索引擎
    具有高质量内容清洗、事实提炼与直接即时回答能力。
    """
    api_key = (settings.TAVILY_API_KEY or "").strip()
    if not api_key:
        return None, []

    from tavily import TavilyClient

    client = TavilyClient(api_key=api_key)
    # 调用 Tavily 官方检索接口（包含直接 AI 答复 include_answer）
    resp = client.search(
        query=query,
        max_results=max_results,
        include_answer=True,
        search_depth="basic",
    )

    answer = resp.get("answer") or None
    raw_results = resp.get("results") or []
    results: List[Dict[str, str]] = []

    for r in raw_results:
        title = r.get("title") or ""
        url = r.get("url") or ""
        content = r.get("content") or ""
        if title or content:
            results.append({
                "title": title,
                "href": url,
                "body": content,
            })

    return answer, results


def _search_bing_cn(query: str, max_results: int = 5, timeout: float = 4.5) -> List[Dict[str, str]]:
    """
    第二优先级（兜底回退）：国内高可用搜索引擎（Bing 中国版直连）
    无需 API Key、无需代理科学上网，国内响应通常在 200ms~500ms。
    """
    url = "https://cn.bing.com/search"
    params = {"q": query, "ensearch": 0}
    headers = {
        "User-Agent": _USER_AGENTS[0],
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Cache-Control": "max-age=0",
    }

    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    if resp.status_code != 200:
        logger.warning(f"[WebSearch/BingCN] 响应异常状态码: {resp.status_code}")
        return []

    tree = html.fromstring(resp.text)
    items = tree.xpath("//li[contains(@class, 'b_algo')]")
    results = []

    for item in items:
        titles = item.xpath(".//h2//text()")
        title = "".join(titles).strip()
        links = item.xpath(".//h2//a/@href")
        link = links[0] if links else ""
        snippets = item.xpath(".//div[contains(@class, 'b_caption')]//p//text() | .//p//text()")
        snippet = "".join(snippets).strip()

        if title and (link or snippet):
            results.append({
                "title": title,
                "href": link,
                "body": snippet,
            })

        if len(results) >= max_results:
            break

    return results


@tool
def web_search(query: str, max_results: int = 5) -> str:
    """
    通过公开互联网搜索实时新闻、时效性资讯、全网最新动态或外部公开网页。
    首选 Tavily AI 原生搜索，若未配置或异常则自动无缝降级到国内必应（Bing CN）直连引擎。

    【核心限制与知识库让位原则】：
    若用户提问的主题（如技术概念、架构、学习资料）在本地私有知识库中已有收录文档，必须优先调用 `query_knowledge_base`，严禁越过本地知识库直接搜索外网！
    只有当本地知识库未命中、或用户明确要求查阅“互联网最新全网资讯/实时新闻”时，才调用本工具。

    参数:
        query: 搜索关键词或查询短语
        max_results: 返回的最大结果条数（默认 5 条）
    """
    clean_query = (query or "").strip()
    if not clean_query:
        return "网络检索失败：搜索关键词不能为空。"

    # 1. 检查内存缓存 (命中则 0ms 瞬间返回)
    cache_key = clean_query.lower()
    now = time.time()
    if cache_key in _SEARCH_CACHE:
        cached_time, cached_res = _SEARCH_CACHE[cache_key]
        if now - cached_time < _CACHE_TTL:
            _SEARCH_CACHE.move_to_end(cache_key)
            logger.info(f"[WebSearch] 命中内存缓存: '{clean_query}'")
            return cached_res

    results: List[Dict[str, str]] = []
    tavily_answer: Optional[str] = None
    engine_used = "BingCN"

    # 2. 第一优先级：尝试 Tavily AI 原生搜索 (高质量正文与问答)
    if settings.TAVILY_API_KEY and settings.TAVILY_API_KEY.strip():
        try:
            logger.info(f"[WebSearch] 正在尝试使用 Tavily AI 检索: '{clean_query}'")
            tavily_answer, results = _search_tavily(clean_query, max_results=max_results, timeout=6.0)
            if results:
                engine_used = "Tavily"
        except Exception as e:
            logger.warning(f"[WebSearch] Tavily 检索异常 ({e})，正在自动无缝降级到 Bing CN 国内直连搜索...")

    # 3. 第二优先级（回退兜底）：国内必应 (Bing CN) 直连搜索 (免 Key，高可用)
    if not results:
        try:
            logger.info(f"[WebSearch] 正在使用 Bing CN 国内直连检索: '{clean_query}'")
            results = _search_bing_cn(clean_query, max_results=max_results, timeout=4.5)
            if results:
                engine_used = "BingCN"
        except Exception as e:
            logger.warning(f"[WebSearch] Bing CN 国内搜索请求异常: {e}")

    # 4. 格式化输出
    if not results:
        res_text = f"未找到与关键词 '{clean_query}' 相关的公开检索结果，请尝试简化关键词或基于已有专业知识分析解答。"
        _SEARCH_CACHE[cache_key] = (now, res_text)
        return res_text

    formatted = []
    if tavily_answer:
        formatted.append(f"【AI综述/即时回答】: {tavily_answer}\n")

    for i, r in enumerate(results, 1):
        title = r.get("title") or "无标题"
        body = r.get("body") or "无描述信息"
        href = r.get("href") or ""
        formatted.append(f"[{i}] {title}\n链接: {href}\n摘要: {body}\n")

    res_text = "\n".join(formatted)

    # 5. 写入内存缓存
    _SEARCH_CACHE[cache_key] = (now, res_text)
    if len(_SEARCH_CACHE) > _CACHE_MAX_SIZE:
        _SEARCH_CACHE.popitem(last=False)

    logger.info(f"[WebSearch] 检索完成 (引擎: {engine_used}, 结果数: {len(results)}, query='{clean_query}')")
    return res_text
