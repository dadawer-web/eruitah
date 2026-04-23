"""
Eruitah 智能编程沙盒 - FastAPI Web 服务 v4

v4 完全重写: 对齐用户伪代码的"神经系统"模式

架构:
┌──────────────┐    WebSocket     ┌──────────────────┐     API      ┌──────────┐
│  Qt/C++ 客户端 │ <─────────────> │  FastAPI (本模块)  │ ──────────> │  LLM API  │
│  Monaco Editor │   双向实时通信   │  main.py v4       │ <────────── │  Claude   │
└──────────────┘                  └──────────────────┘              └──────────┘

核心设计:
  run_agent() 是同步生成器 → 通过 run_in_executor 放入线程池执行
  → 主线程 async for 遍历 → websocket.send_json() 实时推送

WebSocket 事件 (直接从 run_agent yield 出来):
  {"type": "status",     "data": "Agent 正在思考..."}
  {"type": "message",    "content": "大模型回复"}
  {"type": "tool_start", "tool_name": "bash", "args": {...}}
  {"type": "tool_end",   "tool_name": "bash", "result": "...", "is_error": false}
  {"type": "finish",     "data": "最终结果"}
  {"type": "error",      "data": "错误信息"}
"""

import os
import json
import asyncio
import logging
import uuid
from typing import Optional
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env 文件（优先从项目根目录加载）
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
    print(f"已加载环境变量文件: {env_path}")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agent_runner import run_agent, MAX_TURNS

logger = logging.getLogger(__name__)

# ============================================================================
# 配置
# ============================================================================

SANDBOX_DIR = os.environ.get("ERUITAH_SANDBOX_DIR", "/tmp/eruitah-sandbox")
API_PROVIDER = os.environ.get("ERUITAH_API_PROVIDER", "openai")
DEFAULT_MODEL_OPENAI = os.environ.get("ERUITAH_MODEL_OPENAI", "gpt-4o")
DEFAULT_MODEL_ANTHROPIC = os.environ.get("ERUITAH_MODEL_ANTHROPIC", "claude-sonnet-4-20250514")


# ============================================================================
# 请求模型
# ============================================================================

class ExecuteRequest(BaseModel):
    prompt: str = Field(..., description="用户提示词", min_length=1)
    work_dir: Optional[str] = Field(None, description="工作目录")
    max_turns: int = Field(MAX_TURNS, description="最大循环轮数", ge=1, le=50)
    api_key: Optional[str] = Field(None, description="API Key")
    model: Optional[str] = Field(None, description="模型名称")
    base_url: Optional[str] = Field(None, description="API 基础 URL")
    provider: Optional[str] = Field(None, description="API 提供商: openai 或 anthropic")


class HealthResponse(BaseModel):
    status: str = "ok"
    sandbox_dir: str = ""
    api_provider: str = ""


# ============================================================================
# 应用生命周期
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs(SANDBOX_DIR, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info(f"Eruitah 沙盒服务 v4 启动，工作目录: {SANDBOX_DIR}")
    yield
    logger.info("Eruitah 沙盒服务关闭")


app = FastAPI(
    title="Eruitah 智能编程沙盒",
    description="基于 Claude Code 核心逻辑的 AI 编程沙盒微服务 v4",
    version="4.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ============================================================================
# 同步生成器 → 异步迭代器 适配器
# ============================================================================

async def _run_agent_async(
    user_input: str,
    work_dir: str = ".",
    max_turns: int = MAX_TURNS,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    provider: str = "openai",
):
    """
    将同步生成器 run_agent() 包装为异步迭代器

    核心问题: run_agent() 是同步函数，内部调用 LLM API 会阻塞事件循环。
    解决方案: 使用 asyncio.Queue + 线程池

    ┌─────────────────┐         ┌──────────────────────┐
    │  主线程 (async)  │         │  工作线程 (sync)      │
    │                  │         │                      │
    │  async for e:   │  ←Queue─  │  for e in run_agent: │
    │    send_json(e) │         │    queue.put(e)      │
    │                  │         │                      │
    └─────────────────┘         └──────────────────────┘

    这样 LLM API 的阻塞调用在工作线程中执行，
    主线程的 WebSocket 心跳不会被卡住。
    """
    queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def _sync_worker():
        try:
            for event in run_agent(
                user_input=user_input,
                work_dir=work_dir,
                max_turns=max_turns,
                api_key=api_key,
                model=model,
                base_url=base_url,
                provider=provider,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except Exception as e:
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": "error", "data": f"Agent 内部异常: {str(e)}"},
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    # 在线程池中启动同步生成器
    import concurrent.futures
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    loop.run_in_executor(executor, _sync_worker)

    # 从队列中消费事件
    while True:
        event = await queue.get()
        if event is None:
            break
        yield event


# ============================================================================
# WebSocket 端点 - /ws/coding
# ============================================================================

@app.websocket("/ws/coding")
async def websocket_coding(websocket: WebSocket):
    """
    WebSocket 双向通信 - Agent 的"神经系统"

    协议:
      客户端发送: {"task": "写一个二叉树", "model": "gpt-4o", ...}
      服务端推送: {"type": "status", "data": "Agent 正在思考..."}
                 {"type": "tool_start", "tool_name": "bash", "args": {...}}
                 {"type": "tool_end", "tool_name": "bash", "result": "...", "is_error": false}
                 {"type": "finish", "data": "最终结果"}

    Qt/C++ 对接示例:
        void CodingLabWindow::onTextMessageReceived(QString message) {
            QJsonObject obj = QJsonDocument::fromJson(message.toUtf8()).object();
            QString type = obj["type"].toString();

            if (type == "tool_start") {
                // 显示: Agent 正在使用 bash 工具...
                QString toolName = obj["tool_name"].toString();
                ui->statusLabel->setText("正在执行: " + toolName);
            }
            else if (type == "tool_end") {
                // 显示工具执行结果
                bool isError = obj["is_error"].toBool();
                QString result = obj["result"].toString();
                if (isError) {
                    appendTerminalLog("[ERROR] " + result);
                } else {
                    appendTerminalLog(result);
                }
            }
            else if (type == "finish") {
                ui->statusLabel->setText("任务完成");
            }
        }
    """
    await websocket.accept()
    
    # 用于接收客户端消息的任务
    client_message_queue = asyncio.Queue()
    
    async def receive_client_messages():
        """持续接收客户端消息"""
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    data = json.loads(raw)
                    await client_message_queue.put(data)
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
    
    # 启动接收任务
    receive_task = asyncio.create_task(receive_client_messages())
    
    try:
        # 等待第一条消息（任务）
        data = await client_message_queue.get()
        
        # 解析任务
        user_input = data.get("task") or data.get("prompt") or ""
        if not user_input:
            await websocket.send_json({"type": "error", "data": "task/prompt 不能为空"})
            return

        # 解析参数
        work_dir = data.get("work_dir", SANDBOX_DIR)
        max_turns = data.get("max_turns", MAX_TURNS)
        api_key = data.get("api_key") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        model = data.get("model")
        base_url = data.get("base_url") or os.environ.get("OPENAI_BASE_URL")
        provider = data.get("provider", API_PROVIDER)

        if not model:
            model = DEFAULT_MODEL_ANTHROPIC if provider == "anthropic" else DEFAULT_MODEL_OPENAI

        # 确保 base_url 有 /v1 后缀（通义千问兼容模式需要）
        if base_url and not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"

        os.makedirs(work_dir, exist_ok=True)

        # 启动 Agent 死循环，实时推送事件
        async for event in _run_agent_async(
            user_input=user_input,
            work_dir=work_dir,
            max_turns=max_turns,
            api_key=api_key,
            model=model,
            base_url=base_url,
            provider=provider,
        ):
            await websocket.send_json(event)
            
            if event.get("type") == "ask_user":
                question_id = event.get("data", {}).get("question_id", "")
                
                while True:
                    try:
                        msg = await asyncio.wait_for(client_message_queue.get(), timeout=300)
                        if msg.get("type") == "user_answer" and msg.get("question_id") == question_id:
                            from ask_user_tool import resolve_question
                            resolve_question(question_id, msg.get("answer", ""))
                            break
                    except asyncio.TimeoutError:
                        await websocket.send_json({"type": "error", "data": "等待用户回答超时"})
                        break
            
            if event.get("type") == "command_confirmation":
                confirmation_id = str(uuid.uuid4())[:8]
                event["data"]["confirmation_id"] = confirmation_id
                await websocket.send_json(event)
                
                while True:
                    try:
                        msg = await asyncio.wait_for(client_message_queue.get(), timeout=300)
                        if msg.get("type") == "command_confirm" and msg.get("confirmation_id") == confirmation_id:
                            if msg.get("approved"):
                                from bash_executor import execute_bash
                                result = execute_bash(
                                    event["data"]["command"],
                                    work_dir=work_dir,
                                    allow_warnings=True
                                )
                                if result.blocked:
                                    await websocket.send_json({
                                        "type": "tool_end",
                                        "tool_name": "bash",
                                        "result": f"命令被拦截: {result.block_reason}",
                                        "is_error": True
                                    })
                                else:
                                    output = result.stdout
                                    if result.stderr:
                                        output += f"\n[stderr]\n{result.stderr}"
                                    await websocket.send_json({
                                        "type": "tool_end",
                                        "tool_name": "bash",
                                        "result": output or "命令执行成功",
                                        "is_error": result.exit_code != 0
                                    })
                            else:
                                await websocket.send_json({
                                    "type": "tool_end",
                                    "tool_name": "bash",
                                    "result": "用户拒绝执行此命令",
                                    "is_error": True
                                })
                            break
                    except asyncio.TimeoutError:
                        await websocket.send_json({"type": "error", "data": "等待用户确认超时"})
                        break
            
            await asyncio.sleep(0.01)

    except WebSocketDisconnect:
        logger.info("WebSocket 客户端断开连接")
    except Exception as e:
        logger.error(f"WebSocket 异常: {e}")
        try:
            await websocket.send_json({"type": "error", "data": str(e)})
        except Exception:
            pass
    finally:
        receive_task.cancel()
        from ask_user_tool import cancel_all_questions
        cancel_all_questions()
        try:
            await websocket.close()
        except Exception:
            pass


# ============================================================================
# WebSocket 端点 - 长连接多任务模式
# ============================================================================

@app.websocket("/ws/coding/persistent")
async def websocket_coding_persistent(websocket: WebSocket):
    """
    持久 WebSocket 连接 - 支持在一个连接上发送多个任务

    协议:
      客户端发送: {"action": "run", "task": "写一个二叉树", ...}
      客户端发送: {"action": "ping"}
      服务端推送: {"type": "pong"}
      服务端推送: {"type": "finish", "data": "...", "task_id": "xxx"}
    """
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "data": "无效的 JSON 格式"})
                continue

            action = data.get("action", "")

            if action == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if action == "close":
                break

            # 解析任务
            user_input = data.get("task") or data.get("prompt") or ""
            if not user_input:
                await websocket.send_json({"type": "error", "data": "task/prompt 不能为空"})
                continue

            work_dir = data.get("work_dir", SANDBOX_DIR)
            max_turns = data.get("max_turns", MAX_TURNS)
            api_key = data.get("api_key") or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
            model = data.get("model")
            base_url = data.get("base_url") or os.environ.get("OPENAI_BASE_URL")
            provider = data.get("provider", API_PROVIDER)

            if not model:
                model = DEFAULT_MODEL_ANTHROPIC if provider == "anthropic" else DEFAULT_MODEL_OPENAI

            # 确保 base_url 有 /v1 后缀（通义千问兼容模式需要）
            if base_url and not base_url.endswith("/v1"):
                base_url = base_url.rstrip("/") + "/v1"

            os.makedirs(work_dir, exist_ok=True)

            # 启动 Agent
            async for event in _run_agent_async(
                user_input=user_input,
                work_dir=work_dir,
                max_turns=max_turns,
                api_key=api_key,
                model=model,
                base_url=base_url,
                provider=provider,
            ):
                await websocket.send_json(event)
                await asyncio.sleep(0.01)

    except WebSocketDisconnect:
        logger.info("持久 WebSocket 客户端断开连接")
    except Exception as e:
        logger.error(f"持久 WebSocket 异常: {e}")
        try:
            await websocket.send_json({"type": "error", "data": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


# ============================================================================
# REST API 端点 - 同步模式
# ============================================================================

@app.post("/api/v1/execute")
async def execute_sync(request: ExecuteRequest):
    """
    同步执行模式 - 等待 Agent 完成后返回最终结果

    适用于不需要实时流式推送的场景（如 CI/CD、批量任务）
    """
    work_dir = request.work_dir or SANDBOX_DIR
    provider = request.provider or API_PROVIDER
    model = request.model or (DEFAULT_MODEL_ANTHROPIC if provider == "anthropic" else DEFAULT_MODEL_OPENAI)
    api_key = request.api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    base_url = request.base_url or os.environ.get("OPENAI_BASE_URL")

    # 确保 base_url 有 /v1 后缀（通义千问兼容模式需要）
    if base_url and not base_url.endswith("/v1"):
        base_url = base_url.rstrip("/") + "/v1"

    os.makedirs(work_dir, exist_ok=True)

    final_result = None
    all_events = []

    async for event in _run_agent_async(
        user_input=request.prompt,
        work_dir=work_dir,
        max_turns=request.max_turns,
        api_key=api_key,
        model=model,
        base_url=base_url,
        provider=provider,
    ):
        all_events.append(event)
        if event.get("type") in ("finish", "error"):
            final_result = event

    if final_result is None:
        return {"success": False, "message": "Agent 未产生最终结果", "events": all_events}

    return {
        "success": final_result.get("type") == "finish",
        "message": final_result.get("data", ""),
        "events": all_events,
    }


# ============================================================================
# 文件管理 API
# ============================================================================

@app.get("/api/v1/files")
async def list_files(path: str = SANDBOX_DIR):
    """获取目录下的所有文件列表"""
    import os
    from pathlib import Path
    
    try:
        base_path = Path(path)
        if not base_path.exists():
            base_path.mkdir(parents=True, exist_ok=True)
            return {"files": []}
        
        files = []
        for root, dirs, filenames in os.walk(base_path):
            for filename in filenames:
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, base_path)
                files.append(rel_path)
        
        return {"files": sorted(files)}
    except Exception as e:
        return {"files": [], "error": str(e)}


@app.get("/api/v1/browse")
async def browse_directory(path: str = "/"):
    """浏览文件系统，返回指定目录下的所有文件夹"""
    import os
    from pathlib import Path
    
    try:
        base_path = Path(path)
        if not base_path.exists():
            return {"folders": [], "error": f"路径不存在: {path}"}
        
        if not base_path.is_dir():
            return {"folders": [], "error": f"不是目录: {path}"}
        
        folders = []
        try:
            for item in base_path.iterdir():
                if item.is_dir():
                    try:
                        folders.append({
                            "name": item.name,
                            "path": str(item.absolute()),
                        })
                    except PermissionError:
                        continue
        except PermissionError:
            return {"folders": [], "error": f"无权限访问: {path}"}
        
        folders.sort(key=lambda x: x["name"].lower())
        return {"folders": folders, "current_path": str(base_path.absolute())}
    except Exception as e:
        return {"folders": [], "error": str(e)}


@app.get("/api/v1/file")
async def read_file_content(path: str):
    """读取文件内容"""
    import os
    
    try:
        if not os.path.exists(path):
            return {"error": "文件不存在"}
        
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        
        return {"content": content, "path": path}
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# 健康检查
# ============================================================================

@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(sandbox_dir=SANDBOX_DIR, api_provider=API_PROVIDER)


@app.get("/")
async def root():
    return {
        "name": "Eruitah 智能编程沙盒",
        "version": "4.0.0",
        "endpoints": {
            "ide": "/ide",
            "websocket": "/ws/coding",
            "websocket_persistent": "/ws/coding/persistent",
            "execute": "/api/v1/execute",
            "health": "/api/v1/health",
        },
    }


@app.get("/ide")
async def ide_page():
    """IDE 界面 - 返回 coding_lab.html"""
    from fastapi.responses import FileResponse
    html_path = os.path.join(STATIC_DIR, "coding_lab.html")
    if os.path.isfile(html_path):
        return FileResponse(html_path, media_type="text/html")
    return {"error": "coding_lab.html not found", "hint": "请确保 static/coding_lab.html 存在"}


@app.websocket("/ws/terminal")
async def websocket_terminal(websocket: WebSocket):
    """
    交互式终端 WebSocket - 真正的 shell 体验
    
    协议:
      客户端发送: {"type": "input", "data": "ls\n"}
                 {"type": "resize", "cols": 120, "rows": 40}
      服务端推送: {"type": "output", "data": "file1\nfile2\n"}
    """
    from interactive_terminal import InteractiveTerminal
    
    await websocket.accept()
    
    pty_session = None
    output_task = None
    
    async def read_output():
        """持续读取 PTY 输出并发送给前端"""
        while pty_session and pty_session.running:
            try:
                output = pty_session.read(timeout=0.05)
                if output:
                    await websocket.send_json({"type": "output", "data": output})
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"读取 PTY 输出失败: {e}")
                break
    
    try:
        data = await websocket.receive_json()
        
        if data.get("type") == "start":
            work_dir = data.get("work_dir", SANDBOX_DIR)
            cols = data.get("cols", 80)
            rows = data.get("rows", 24)
            shell = data.get("shell")
            
            pty_session = InteractiveTerminal(
                work_dir=work_dir,
                shell=shell,
                cols=cols,
                rows=rows
            )
            
            if pty_session.start():
                await websocket.send_json({
                    "type": "started",
                    "data": {
                        "pid": pty_session.pid,
                        "shell": pty_session.shell,
                        "cwd": pty_session.work_dir
                    }
                })
                output_task = asyncio.create_task(read_output())
            else:
                await websocket.send_json({"type": "error", "data": "启动终端失败"})
                return
        
        while True:
            try:
                data = await websocket.receive_json()
                
                if data.get("type") == "input":
                    input_data = data.get("data", "")
                    if pty_session and input_data:
                        pty_session.write(input_data)
                
                elif data.get("type") == "resize":
                    cols = data.get("cols", 80)
                    rows = data.get("rows", 24)
                    if pty_session:
                        pty_session.resize(cols, rows)
                
            except Exception as e:
                logger.error(f"处理终端消息失败: {e}")
                break
                
    except WebSocketDisconnect:
        logger.info("交互式终端 WebSocket 断开")
    except Exception as e:
        logger.error(f"交互式终端异常: {e}")
    finally:
        if output_task:
            output_task.cancel()
        if pty_session:
            pty_session.stop()
        try:
            await websocket.close()
        except Exception:
            pass


# ============================================================================
# 入口
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    # 启动命令:
    #   python3 main.py
    #
    # 或:
    #   uvicorn main:app --host 0.0.0.0 --port 8001 --reload
    #
    # 环境变量:
    #   export ERUITAH_SANDBOX_DIR=/tmp/eruitah-sandbox
    #   export ERUITAH_API_PROVIDER=openai
    #   export OPENAI_API_KEY=sk-xxx

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info",
    )
