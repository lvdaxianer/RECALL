"""
Retrieval answer synthesis tests.
"""

import pytest

from app.services.retrieval_answer_service import RetrievalAnswerService, filter_results_for_answer


class FakeLLMService:
    """Fake LLM that returns a configurable answer."""

    def __init__(self, answer: str):
        self.answer = answer
        self.prompts: list[str] = []

    async def chat_simple(self, prompt: str, system: str | None = None):
        self.prompts.append(prompt)
        return self.answer


class FakeStreamingLLMService:
    """Fake LLM that exposes streaming chunks and fails if non-streaming is used."""

    def __init__(self, chunks: list[str]):
        self.chunks = chunks
        self.prompts: list[str] = []

    async def chat_simple(self, prompt: str, system: str | None = None):
        raise AssertionError("stream_synthesize should not call chat_simple")

    async def stream_chat_simple(self, prompt: str, system: str | None = None):
        self.prompts.append(prompt)
        for chunk in self.chunks:
            yield chunk


def test_intro_question_keeps_same_document_context_sections_for_answer():
    """介绍类问题应保留同文档正文片段，不能只给答案生成标题摘要。"""
    results = [
        {
            "chunk_id": "chunk-1",
            "document_name": "03.负载均衡技术.md",
            "title": "负载均衡技术(L4 vs L7)",
            "content": "本文详细对比四层负载均衡和七层负载均衡的工作原理、优缺点及适用场景。",
        },
        {
            "chunk_id": "chunk-2",
            "document_name": "03.负载均衡技术.md",
            "title": "1.1 什么是负载均衡?",
            "content": "负载均衡是将网络流量或请求分发到多个服务器的技术。",
        },
        {
            "chunk_id": "chunk-3",
            "document_name": "03.负载均衡技术.md",
            "title": "2.1 什么是四层负载均衡?",
            "content": "四层负载均衡基于 IP 地址和端口号进行路由决策。",
        },
    ]

    filtered = filter_results_for_answer("介绍下 负载均衡技术", results)

    assert [result["chunk_id"] for result in filtered] == ["chunk-1", "chunk-2", "chunk-3"]


@pytest.mark.asyncio
async def test_intro_question_prompt_keeps_same_document_context_sections():
    """介绍类问题的 Prompt 应保留同文档多个正文片段供模型展开。"""
    llm = FakeLLMService("已有充分介绍。")
    service = RetrievalAnswerService(llm_service=llm)

    await service.synthesize(
        "介绍下 负载均衡技术",
        [
            {
                "chunk_id": "chunk-1",
                "document_name": "03.负载均衡技术.md",
                "title": "负载均衡技术(L4 vs L7)",
                "content": "本文详细对比四层负载均衡和七层负载均衡的工作原理、优缺点及适用场景。",
            },
            {
                "chunk_id": "chunk-2",
                "document_name": "03.负载均衡技术.md",
                "title": "1.1 什么是负载均衡?",
                "content": "负载均衡是将网络流量或请求分发到多个服务器的技术。",
            },
            {
                "chunk_id": "chunk-3",
                "document_name": "03.负载均衡技术.md",
                "title": "2.1 什么是四层负载均衡?",
                "content": "四层负载均衡基于 IP 地址和端口号进行路由决策。",
            },
        ],
    )

    prompt = llm.prompts[0]
    assert "网络流量或请求分发到多个服务器" in prompt
    assert "IP 地址和端口号" in prompt


@pytest.mark.asyncio
async def test_intro_question_expands_catalog_like_llm_answer_from_context():
    """介绍类问题如果模型只返回目录式摘要，应基于片段兜底展开正文。"""
    terse_answer = "核心对比：详细对比了四层负载均衡（L4）与七层负载均衡（L7）。\n涵盖维度：\n工作原理\n优缺点分析\n适用场景"
    service = RetrievalAnswerService(llm_service=FakeLLMService(terse_answer))

    result = await service.synthesize(
        "介绍下 负载均衡技术",
        [
            {
                "chunk_id": "chunk-1",
                "document_name": "03.负载均衡技术.md",
                "title": "1.1 什么是负载均衡?",
                "content": (
                    "负载均衡(Load Balancing)是将网络流量或请求分发到多个服务器的技术,旨在: "
                    "- 提高可用性: 单台服务器故障不影响整体服务 "
                    "- 提升性能: 充分利用多台服务器的处理能力 "
                    "- 实现扩展: 灵活增减服务器数量"
                ),
            },
            {
                "chunk_id": "chunk-2",
                "document_name": "03.负载均衡技术.md",
                "title": "2.1 什么是四层负载均衡?",
                "content": "四层负载均衡工作在 OSI 模型的传输层, 主要基于 IP 地址和端口号进行路由决策。",
            },
            {
                "chunk_id": "chunk-3",
                "document_name": "03.负载均衡技术.md",
                "title": "3.1 什么是七层负载均衡?",
                "content": "七层负载均衡工作在应用层, 可以根据 HTTP 路径、Header、Cookie 等应用层信息转发请求。",
            },
        ],
    )

    assert len(result["answer"]) > len(terse_answer)
    assert "提高可用性" in result["answer"]
    assert "IP 地址和端口号" in result["answer"]
    assert "HTTP 路径" in result["answer"]


@pytest.mark.asyncio
async def test_intro_question_stream_expands_catalog_like_llm_answer_from_context():
    """聊天页流式回答遇到目录式摘要时，也应基于片段输出展开说明。"""
    terse_answer = "核心对比：L4 与 L7。\n涵盖维度：\n工作原理\n优缺点分析\n适用场景"
    service = RetrievalAnswerService(llm_service=FakeStreamingLLMService([terse_answer]))

    deltas = [
        delta["text"]
        async for delta in service.stream_synthesize(
            "介绍下 负载均衡技术",
            [
                {
                    "chunk_id": "chunk-1",
                    "document_name": "03.负载均衡技术.md",
                    "title": "1.1 什么是负载均衡?",
                    "content": "负载均衡是将网络流量或请求分发到多个服务器的技术, 可以提高可用性、提升性能并实现扩展。",
                },
                {
                    "chunk_id": "chunk-2",
                    "document_name": "03.负载均衡技术.md",
                    "title": "2.1 什么是四层负载均衡?",
                    "content": "四层负载均衡基于 IP 地址和端口号进行路由决策, 不关心应用层协议内容。",
                },
            ],
        )
    ]

    answer = "".join(deltas)
    assert len(answer) > len(terse_answer)
    assert "提高可用性" in answer
    assert "IP 地址和端口号" in answer


@pytest.mark.asyncio
async def test_intro_question_expands_polished_but_thin_catalog_answer():
    """介绍类问题即使模型输出较长目录，也应补充命中片段里的实质定义和机制。"""
    thin_answer = (
        "基于提供的知识库片段，关于负载均衡技术的介绍如下：\n\n"
        "* **核心主题**：主要涉及四层负载均衡与七层负载均衡的对比分析。\n"
        "* **关键内容**：\n"
        "  * **工作原理**：详细阐述了两者的运作机制差异。\n"
        "  * **优缺点评估**：分析了各自的技术优势与局限性。\n"
        "  * **适用场景**：明确了在不同业务需求下如何选择四层或七层负载均衡方案。\n"
        "整体来看，资料围绕 L4 与 L7 的核心差异展开。"
    )
    service = RetrievalAnswerService(llm_service=FakeLLMService(thin_answer))

    result = await service.synthesize(
        "介绍下 负载均衡技术",
        [
            {
                "chunk_id": "chunk-1",
                "document_name": "03.负载均衡技术.md",
                "title": "1.1 什么是负载均衡?",
                "content": "负载均衡是将网络流量或请求分发到多个服务器的技术, 旨在提高可用性、提升性能并实现扩展。",
            },
            {
                "chunk_id": "chunk-2",
                "document_name": "03.负载均衡技术.md",
                "title": "2.1 什么是四层负载均衡?",
                "content": "四层负载均衡工作在 OSI 模型的传输层, 主要基于 IP 地址和端口号进行路由决策。",
            },
        ],
    )

    assert "网络流量或请求分发到多个服务器" in result["answer"]
    assert "IP 地址和端口号" in result["answer"]


@pytest.mark.asyncio
async def test_overview_answer_uses_titles_when_chunks_have_empty_content():
    """概览问题即使命中的是标题型 chunk，也应返回可读主题摘要。"""
    service = RetrievalAnswerService(llm_service=FakeLLMService(""))

    result = await service.synthesize(
        "这个知识库主要包含什么？",
        [
            {
                "chunk_id": "chunk-1",
                "document_name": "笔记/AI/扩展知识/微调/00.为什么需要微调以及与知识库的区别.md",
                "title": "三、微调 vs 知识库（RAG）",
                "content": "",
                "description": "",
            },
            {
                "chunk_id": "chunk-2",
                "document_name": "笔记/AI/扩展知识/微调/00.为什么需要微调以及与知识库的区别.md",
                "title": "二、为什么需要微调（Fine-tuning）",
                "content": "",
                "description": "",
            },
        ],
    )

    assert "微调 vs 知识库" in result["answer"]
    assert "为什么需要微调" in result["answer"]
    assert "笔记/AI/扩展知识" not in result["answer"]


@pytest.mark.asyncio
async def test_specific_answer_filters_unrelated_context_before_llm_prompt():
    """具体问题只应把相关片段交给 LLM，避免回答里复述无关命中。"""
    llm = FakeLLMService("根据现有资料，无法回答 JMM 访问策略的细节。")
    service = RetrievalAnswerService(llm_service=llm)

    await service.synthesize(
        "JMM 访问策略是啥",
        [
            {
                "chunk_id": "chunk-1",
                "document_name": "jmm.md",
                "title": "Java 内存模型（JMM）",
                "content": "",
            },
            {
                "chunk_id": "chunk-2",
                "document_name": "linux.md",
                "title": "mmap 原理",
                "content": "mmap 是 Linux 内存映射机制。",
            },
            {
                "chunk_id": "chunk-3",
                "document_name": "redis.md",
                "title": "Redis 过期键删除策略",
                "content": "Redis 过期键删除策略包含惰性删除和定期删除。",
            },
        ],
    )

    prompt = llm.prompts[0]
    assert "Java 内存模型" in prompt
    assert "mmap" not in prompt
    assert "Redis" not in prompt


@pytest.mark.asyncio
async def test_answer_service_splits_long_answer_into_streaming_deltas():
    """长答案应拆成多个 answer.delta，避免前端整段突然出现。"""
    long_answer = "这个知识库主要包含：" + "微调、知识库、RAG。" * 20
    service = RetrievalAnswerService(llm_service=FakeLLMService(long_answer))

    result = await service.synthesize(
        "这个知识库主要包含什么？",
        [{
            "chunk_id": "chunk-1",
            "document_name": "guide.md",
            "title": "微调 vs 知识库",
            "content": "微调用于风格学习，知识库用于可更新事实。",
        }],
    )

    assert len(result["deltas"]) > 1
    assert "".join(delta["text"] for delta in result["deltas"]) == result["answer"]


@pytest.mark.asyncio
async def test_answer_service_streams_llm_chunks_directly():
    """流式答案应直接转发 LLM 增量片段，而不是等待完整答案再拆分。"""
    service = RetrievalAnswerService(llm_service=FakeStreamingLLMService(["## 概览\n", "**RAG**", " 与微调"]))

    deltas = [
        delta
        async for delta in service.stream_synthesize(
            "这个知识库主要包含什么？",
            [{
                "chunk_id": "chunk-1",
                "document_name": "guide.md",
                "title": "微调 vs 知识库",
                "content": "微调用于风格学习，知识库用于可更新事实。",
            }],
        )
    ]

    assert [delta["text"] for delta in deltas] == ["## 概览\n", "**RAG**", " 与微调"]
    assert all(delta["chunk_id"] == "chunk-1" for delta in deltas)


@pytest.mark.asyncio
async def test_answer_service_splits_large_streaming_llm_chunk():
    """当模型端一次返回大块文本时，答案服务仍应拆成可感知的流式片段。"""
    long_chunk = "该知识库主要包含：" + "微调、知识库、RAG。" * 20
    service = RetrievalAnswerService(llm_service=FakeStreamingLLMService([long_chunk]))

    deltas = [
        delta
        async for delta in service.stream_synthesize(
            "这个知识库主要包含什么？",
            [{
                "chunk_id": "chunk-1",
                "document_name": "guide.md",
                "title": "微调 vs 知识库",
                "content": "微调用于风格学习，知识库用于可更新事实。",
            }],
        )
    ]

    assert len(deltas) > 1
    assert "".join(delta["text"] for delta in deltas) == long_chunk


@pytest.mark.asyncio
async def test_answer_service_keeps_streaming_delta_chunks_compact():
    """长文本 delta 应足够短，让聊天界面呈现接近打字机的连续输出。"""
    long_chunk = "该知识库主要包含：" + "微调、知识库、RAG。" * 20
    service = RetrievalAnswerService(llm_service=FakeStreamingLLMService([long_chunk]))

    deltas = [
        delta
        async for delta in service.stream_synthesize(
            "这个知识库主要包含什么？",
            [{
                "chunk_id": "chunk-1",
                "document_name": "guide.md",
                "title": "微调 vs 知识库",
                "content": "微调用于风格学习，知识库用于可更新事实。",
            }],
        )
    ]

    assert max(len(delta["text"]) for delta in deltas) <= 16


@pytest.mark.asyncio
async def test_answer_service_does_not_split_inline_markdown_tokens():
    """流式拆分不应切断加粗、链接、图片等 Markdown 内联标记。"""
    answer = "该知识库主要围绕**微调（Fine-tuning）**与**知识库/RAG**展开，详见[架构图](https://example.com/a.png)。"
    service = RetrievalAnswerService(llm_service=FakeStreamingLLMService([answer]))

    deltas = [
        delta["text"]
        async for delta in service.stream_synthesize(
            "这个知识库主要包含什么？",
            [{
                "chunk_id": "chunk-1",
                "document_name": "guide.md",
                "title": "微调 vs 知识库",
                "content": "微调用于风格学习，知识库用于可更新事实。",
            }],
        )
    ]

    assert "".join(deltas) == answer
    assert all(text.count("**") in (0, 2) for text in deltas)
    assert all("[架构图](" not in text or text.endswith(")") for text in deltas)
