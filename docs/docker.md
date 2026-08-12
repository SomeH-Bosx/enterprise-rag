# Docker 部署说明

## 推荐方式：本机 Ollama + 容器化 API/UI

原因：

1. **模型体积大**：`qwen2.5:7b` / `nomic-embed-text` 需要单独拉取，放进镜像会显著变慢、难缓存。
2. **GPU/驱动**：Ollama 在宿主机装好后更容易复用本机加速；容器内 GPU 透传依赖环境。
3. **演示稳定性**：本机先 `ollama run` 验证模型可用，再起 API，排障更简单。

步骤：

```bash
# 1) 宿主机
ollama serve   # 若未作为服务运行
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

# 2) 项目根目录
copy .env.example .env   # 填入 DASHSCOPE_API_KEY（可选）
docker compose up --build
```

访问：

- API: http://127.0.0.1:8000/health  
- Streamlit: http://127.0.0.1:8501  

容器内默认通过 `host.docker.internal:11434` 访问宿主机 Ollama（compose 已加 `extra_hosts`）。

## 可选：Ollama 也容器化

```bash
# 需把 api 的 OLLAMA_BASE_URL 指到 ollama 服务
set OLLAMA_BASE_URL=http://ollama:11434
docker compose --profile with-ollama up --build
docker compose exec ollama ollama pull qwen2.5:7b
docker compose exec ollama ollama pull nomic-embed-text
```

注意：首次拉取模型耗时长；无 GPU 时推理会很慢。演示场景优先用本机 Ollama。

## 仅启动 Python API（无 Compose）

```bash
docker build -t enterprise-rag .
docker run --rm -p 8000:8000 --env-file .env ^
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 ^
  -v %cd%/chroma_db:/app/chroma_db ^
  enterprise-rag
```
