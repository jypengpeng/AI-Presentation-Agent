# AI Presentation Agent - 重构版

这是 AI 演示文稿生成器的重构版本，采用高内聚低耦合的架构设计。

## 🚀 Docker 一键启动

### 快速启动

**Windows 用户：**
```bash
cd refactor_version
start.bat
```

**Linux/Mac 用户：**
```bash
cd refactor_version
chmod +x start.sh
./start.sh
```

### 手动启动

1. **配置环境变量**
   ```bash
   cd refactor_version
   cp .env.example .env
   # 编辑 .env 文件，填入你的 OPENAI_API_KEY
   ```

2. **启动服务**
   ```bash
   docker-compose up -d
   ```

3. **访问应用**
   - 前端界面: http://localhost:3000
   - 后端 API: http://localhost:8000
   - API 文档: http://localhost:8000/docs

### 常用命令

```bash
# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 重启服务
docker-compose restart

# 重新构建
docker-compose build --no-cache
```

## 📁 目录结构

```
refactor_version/
├── docker-compose.yml        # Docker 编排配置
├── start.sh / start.bat      # 一键启动脚本
├── .env.example              # 环境变量模板
├── backend/                  # Python 后端 (FastAPI)
│   ├── Dockerfile           # 后端 Docker 配置
│   ├── main.py              # FastAPI 入口
│   ├── config/              # 配置管理
│   │   ├── settings.py      # 环境变量和配置
│   │   └── prompts.py       # 提示词加载
│   ├── core/                # Agent 核心
│   │   ├── agent.py         # Agent 基类
│   │   ├── message.py       # 消息格式化
│   │   └── tool_executor.py # 工具执行引擎
│   ├── tools/               # 工具模块
│   │   ├── base.py          # 工具基类和注册表
│   │   ├── file_tools.py    # 文件操作工具
│   │   ├── command_tools.py # 命令执行工具
│   │   ├── image_tools.py   # 图像生成工具
│   │   └── phase_tools.py   # 阶段控制工具
│   ├── workflow/            # 工作流管理
│   │   ├── phase_manager.py # 阶段状态机
│   │   └── slide_generator.py # 幻灯片生成
│   ├── export/              # 导出功能
│   │   ├── html_exporter.py # HTML 导出
│   │   ├── pptx_exporter.py # PPTX 导出
│   │   ├── speech.py        # 演讲稿生成
│   │   └── zip_exporter.py  # ZIP 打包
│   ├── state/               # 状态管理
│   │   ├── task_manager.py  # 任务管理
│   │   └── manifest.py      # Manifest 管理
│   ├── api/                 # API 路由
│   │   ├── tasks.py         # 任务相关 API
│   │   ├── slides.py        # 幻灯片相关 API
│   │   └── websocket.py     # WebSocket 实时通信
│   └── prompts/             # 提示词文件
│       ├── system_prompt.txt
│       ├── Architect_prompt.md
│       └── Designer.md
├── frontend/                 # React 前端
│   ├── Dockerfile           # 前端 Docker 配置
│   ├── nginx.conf           # Nginx 配置
│   ├── src/
│   │   ├── pages/           # 页面组件
│   │   ├── components/      # 可复用组件
│   │   ├── services/        # API 服务
│   │   └── hooks/           # 自定义 Hooks
│   └── package.json
└── requirements.txt          # Python 依赖
```

## 🛠 本地开发（不使用 Docker）

### 后端

```bash
cd backend
pip install -r ../requirements.txt
uvicorn main:app --reload
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

## 🏗 架构设计

### 工作流阶段

1. **Collecting** - 收集用户输入
2. **Editing Plan** - 编辑演示文稿大纲
3. **Designing** - 生成幻灯片（支持并发）
4. **Completed** - 导出和下载

### 核心模块

- **Config**: 配置和提示词管理
- **Tools**: 模块化的工具系统
- **Core**: Agent 消息处理和工具执行
- **Workflow**: 阶段状态机和生成流程
- **Export**: 多格式导出
- **State**: 任务和状态管理

## 📋 环境变量

| 变量名 | 说明 | 默认值 |
|-------|------|--------|
| OPENAI_API_KEY | OpenAI API 密钥 | (必填) |
| OPENAI_API_BASE | API 地址 | https://api.openai.com/v1 |
| OPENAI_MODEL | 默认模型 | gpt-4o |
| MAX_CONCURRENT_SLIDES | 并发生成数 | 3 |