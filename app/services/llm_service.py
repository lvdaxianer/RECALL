"""
LLM 服务模块

使用 LangChain 的 ChatOpenAI 封装 DashScope API，
支持对话、工具调用（未来 Agent 扩展）

@author lvdaxianerplus
@date 2026-04-15
"""

from typing import AsyncIterator, List, Union, Optional, Any, Callable, Dict, Type
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel, Field
from app.config import Config
from app.utils.logger import get_logger

# 日志器
llm_logger = get_logger("LLM")

# 配置常量
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 2000
DEFAULT_TIMEOUT = 60


class LLMService:
    """
    LLM 服务类

    使用 LangChain ChatOpenAI 封装 DashScope API，
    保持与现有服务（EmbeddingService/RerankService）一致的接口风格。
    """

    def __init__(
        self,
        model_name: str = None,
        api_key: str = None,
        request_url: str = None,
        temperature: float = None,
        max_tokens: int = None,
        timeout: int = None,
        enable_thinking: bool = None,
        streaming: bool = False,
        callbacks: Optional[List[AsyncCallbackHandler]] = None
    ):
        """
        初始化 LLM 服务

        @param model_name - 模型名称（默认从 Config.MODEL_NAME 读取）
        @param api_key - API 密钥（默认从 Config.MODEL_API_KEY 读取）
        @param request_url - 请求 URL（默认从 Config.MODEL_REQUEST_URL 读取）
        @param temperature - 温度参数（默认 0.7）
        @param max_tokens - 最大 token 数（默认 2000）
        @param timeout - 超时时间（秒，默认 60）
        @param enable_thinking - 是否启用模型思考模式
        @param streaming - 是否启用流式输出
        @param callbacks - LangChain 回调处理器
        """
        self.model_name = model_name or Config.MODEL_NAME
        self.api_key = api_key or Config.MODEL_API_KEY
        self.request_url = request_url or Config.MODEL_REQUEST_URL
        self.temperature = temperature if temperature is not None else DEFAULT_TEMPERATURE
        self.max_tokens = max_tokens if max_tokens is not None else DEFAULT_MAX_TOKENS
        self.timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
        self.enable_thinking = enable_thinking if enable_thinking is not None else Config.MODEL_ENABLE_THINKING
        self.streaming = streaming
        self.callbacks = callbacks or []

        # 初始化 LangChain ChatOpenAI
        # DashScope 与 OpenAI API 兼容
        self._client = ChatOpenAI(
            model=self.model_name,
            api_key=self.api_key,
            base_url=self.request_url,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
            extra_body={"enable_thinking": self.enable_thinking},
            streaming=self.streaming,
            callbacks=self.callbacks
        )

        llm_logger.info("[LLM] 初始化完成, model={}, base_url={}",
                      self.model_name, self.request_url)

    async def chat(
        self,
        messages: List[Union[str, Dict[str, str], BaseMessage]],
        **kwargs
    ) -> AIMessage:
        """
        对话接口

        @param messages - 消息列表，支持 str/dict/BaseMessage
        @returns AIMessage
        """
        llm_logger.info("[LLM] 开始对话, 消息数={}", len(messages))

        # 转换消息格式
        lc_messages = self._convert_messages(messages)

        # 调用模型
        response = await self._client.ainvoke(lc_messages, **kwargs)

        llm_logger.info("[LLM] 对话完成")
        return response

    async def chat_simple(
        self,
        prompt: str,
        system: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        简单对话接口（适用于快速调用）

        @param prompt - 用户输入
        @param system - 系统提示（可选）
        @returns 生成的文本
        """
        messages = []
        if system:
            messages.append(SystemMessage(content=system))
        messages.append(HumanMessage(content=prompt))

        response = await self.chat(messages, **kwargs)
        return response.content

    async def stream_chat_simple(
        self,
        prompt: str,
        system: Optional[str] = None,
        **kwargs
    ) -> AsyncIterator[str]:
        """
        简单流式对话接口。

        @param prompt - 用户输入
        @param system - 系统提示（可选）
        @returns 文本增量片段
        """
        messages = []
        if system:
            messages.append(SystemMessage(content=system))
        messages.append(HumanMessage(content=prompt))
        lc_messages = self._convert_messages(messages)

        async for chunk in self._client.astream(lc_messages, **kwargs):
            content = getattr(chunk, "content", "")
            if isinstance(content, str) and content:
                yield content

    async def batch_chat(
        self,
        prompts: List[str],
        system: Optional[str] = None,
        **kwargs
    ) -> List[str]:
        """
        批量对话（并行执行）

        @param prompts - 提示列表
        @param system - 系统提示
        @returns 生成的文本列表
        """
        import asyncio

        async def single_chat(prompt: str) -> str:
            return await self.chat_simple(prompt, system=system, **kwargs)

        tasks = [single_chat(p) for p in prompts]
        results = await asyncio.gather(*tasks)
        return results

    def bind_tools(self, tools: List[BaseTool]) -> "LLMService":
        """
        绑定工具并返回新实例

        @param tools - 工具列表
        @returns 新的 LLMService 实例
        """
        new_service = LLMService(
            model_name=self.model_name,
            api_key=self.api_key,
            request_url=self.request_url,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
            enable_thinking=self.enable_thinking,
            streaming=self.streaming,
            callbacks=self.callbacks
        )
        new_service._client = self._client.bind_tools(tools)
        return new_service

    def with_structured_output(
        self,
        schema: Type[BaseModel]
    ) -> "LLMService":
        """
        绑定结构化输出模式

        @param schema - Pydantic 模型类
        @returns 配置了结构化输出的 LLMService 实例
        """
        new_service = LLMService(
            model_name=self.model_name,
            api_key=self.api_key,
            request_url=self.request_url,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            timeout=self.timeout,
            enable_thinking=self.enable_thinking,
            streaming=self.streaming,
            callbacks=self.callbacks
        )
        new_service._client = self._client.with_structured_output(schema)
        return new_service

    def _convert_messages(
        self,
        messages: List[Union[str, Dict[str, str], BaseMessage]]
    ) -> List[BaseMessage]:
        """
        将不同格式的消息转换为 LangChain 格式

        @param messages - 原始消息列表
        @returns LangChain BaseMessage 列表
        """
        lc_messages = []

        for msg in messages:
            if isinstance(msg, str):
                lc_messages.append(HumanMessage(content=msg))
            elif isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")

                if role == "system":
                    lc_messages.append(SystemMessage(content=content))
                elif role == "user":
                    lc_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    lc_messages.append(AIMessage(content=content))
                elif role == "tool":
                    lc_messages.append(ToolMessage(content=content, tool_call_id=msg.get("tool_call_id")))
            elif isinstance(msg, BaseMessage):
                lc_messages.append(msg)

        return lc_messages

    async def health_check(self) -> bool:
        """
        健康检查

        @returns 服务是否可用
        """
        try:
            response = await self.chat_simple("ping")
            return len(response) > 0
        except Exception as e:
            llm_logger.error("[LLM] 健康检查失败: {}", str(e))
            return False

    @property
    def client(self) -> ChatOpenAI:
        """获取底层 ChatOpenAI 客户端"""
        return self._client

    @property
    def config(self) -> Dict[str, Any]:
        """获取当前配置信息"""
        return {
            "model_name": self.model_name,
            "request_url": self.request_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "enable_thinking": self.enable_thinking,
            "streaming": self.streaming
        }


# 服务实例缓存
_llm_service = None


def get_llm_service() -> LLMService:
    """
    获取 LLM 服务实例（单例）

    @returns LLMService 实例
    """
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
