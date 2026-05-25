# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Changed
- 实现特征标签增强的语义检索 (9e71eaf)

### Changed
- ES 同义词支持本地文件 + Docker IK 分词器 (80d61ce)

- 添加查询缓存和并行化优化 (923502a)

### Changed
- 实现 RRF 混合检索（Milvus 向量 + ES BM25） (288492a)

- 搜索/删除接口添加用户ID路径参数并简化日志 (98304f0)

### Changed
- 添加项目文档和使用说明 (7d473d8)

- 添加 LangChain LLM 服务封装和重试队列 (42650ba)

### Changed
- 添加日志滚动功能 (13a2aa2)

- 插入接口添加用户ID路径参数 (ae2a3ec)

### Changed
- 重构 RAG 路由模块代码结构 (2b93023)

- 完善 RAG 检索功能及日志 (ab27af7)

### Changed
- 更新配置使用阿里云 DashScope 服务 (5643223)

- 初始化 RAG 平台后端服务 (e7235db)

