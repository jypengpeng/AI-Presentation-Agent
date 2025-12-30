# AI Presentation Agent

**让 AI 帮你做 PPT，专注于你的创意和内容。**

一个基于 AI 的智能演示文稿生成器，只需上传参考资料或输入主题，AI 就能自动分析内容、规划大纲、设计专业级幻灯片。

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.11+-green.svg)
![React](https://img.shields.io/badge/React-18.2-blue.svg)
![Docker](https://img.shields.io/badge/Docker-Ready-blue.svg)

---

## ✨ 功能特点

### 🤖 AI 驱动的智能生成
- **自动内容分析**：上传文档/代码/数据，AI 自动提取关键信息
- **智能大纲规划**：基于 Architect 提示词，生成结构化的演示大纲
- **专业幻灯片设计**：Designer Agent 生成 Apple Keynote 风格的专业幻灯片
- **AI 修改助手**：每页幻灯片配备独立的 AI 助手，支持自然语言修改

### 🎨 专业级输出
- **Tailwind CSS + Chart.js**：现代化的视觉设计
- **响应式布局**：支持各种屏幕尺寸
- **丰富的可视化**：图表、卡片、引用框等多种组件
- **多格式导出**：HTML、PPTX、ZIP 打包

### ⚡ 高效并发
- **并发生成**：支持同时生成多张幻灯片（默认 3 并发）
- **实时进度**：WebSocket 推送生成状态
- **断点续传**：失败后可重新生成单张幻灯片

### 🔧 灵活配置
- **模块化架构**：各组件独立可替换
- **多 API 支持**：兼容 OpenAI、Azure、各种第三方 API
- **可自定义提示词**：Architect、Designer、SlideModifier 均可定制

---

## 🖥️ 界面预览

### 工作流程

```
1. 创建任务      2. 上传资料       3. AI 分析规划     4. 编辑大纲
   [新建任务] →    [拖拽上传] →     [自动生成] →     [调整顺序]
       ↓
5. 生成幻灯片    6. 单页编辑       7. AI 修改助手     8. 导出下载
   [并发生成] →    [实时预览] →    [自然语言修改] →    [多格式]
```

### 页面说明

| 页面 | 功能 |
|------|------|
| 任务列表 | 管理所有演示文稿项目 |
| 生成页面 | 输入主题、上传资料、触发 AI 分析 |
| 大纲编辑 | 调整幻灯片顺序、修改标题内容 |
| 网格总览 | 查看所有幻灯片缩略图、启动生成 |
| 单页编辑 | 预览幻灯片、使用 AI 助手修改 |

---

## 🚀 快速开始

### Docker 一键启动（推荐）

**Windows：**
```bash
cd refactor_version
start.bat
```

**Linux/Mac：**
```bash
cd refactor_version
chmod +x start.sh
./start.sh
```

### 手动启动

1. **配置环境变量**
   ```bash
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

# 重新构建（更新代码后）
docker-compose build --no-cache
```

---

## 💻 本地开发

### 后端开发

```bash
cd backend
pip install -r requirements.txt
python run.py
```

### 前端开发

```bash
cd frontend
npm install
npm run dev
```

---

## 📁 项目结构

```
refactor_version/
├── docker-compose.yml        # Docker 编排配置
├── start.sh / start.bat      # 一键启动脚本
├── .env.example              # 环境变量模板
│
├── backend/                  # Python 后端 (FastAPI)
│   ├── main.py              # FastAPI 应用入口
│   ├── run.py               # 开发服务器启动脚本
│   │
│   ├── config/              # 配置管理
│   │   ├── settings.py      # 环境变量和配置
│   │   └── prompts.py       # 提示词加载器
│   │
│   ├── core/                # Agent 核心引擎
│   │   ├── agent.py         # Agent 基类（消息处理、工具调用）
│   │   ├── message.py       # 消息格式化
│   │   └── tool_executor.py # 工具执行引擎
│   │
│   ├── tools/               # 工具模块（可扩展）
│   │   ├── base.py          # 工具基类和注册表
│   │   ├── file_tools.py    # 文件操作（read/write/list）
│   │   ├── command_tools.py # 命令执行
│   │   ├── image_tools.py   # 图像生成（DALL-E）
│   │   └── phase_tools.py   # 阶段控制
│   │
│   ├── workflow/            # 工作流管理
│   │   ├── phase_manager.py # 阶段状态机
│   │   └── slide_generator.py # 并发幻灯片生成
│   │
│   ├── export/              # 导出功能
│   │   ├── html_exporter.py # 合并 HTML 导出
│   │   ├── pptx_exporter.py # PowerPoint 导出
│   │   └── zip_exporter.py  # 资源打包
│   │
│   ├── state/               # 状态管理
│   │   ├── task_manager.py  # 任务 CRUD
│   │   └── manifest.py      # 幻灯片清单管理
│   │
│   ├── api/                 # REST API 路由
│   │   ├── tasks.py         # /tasks/* 任务管理
│   │   ├── slides.py        # /slides/* 幻灯片操作
│   │   ├── agent.py         # /agent/* AI 生成
│   │   ├── upload.py        # /upload/* 文件上传
│   │   └── websocket.py     # WebSocket 实时通信
│   │
│   └── prompts/             # AI 提示词
│       ├── system_prompt.txt    # 收集阶段系统提示
│       ├── Architect_prompt.md  # 大纲规划提示词
│       ├── Designer.md          # 幻灯片设计提示词
│       └── SlideModifier.md     # AI 修改助手提示词
│
├── frontend/                # React 前端
│   ├── src/
│   │   ├── pages/           # 页面组件
│   │   │   ├── TaskListPage.tsx     # 任务列表
│   │   │   ├── GenerationPage.tsx   # 生成/网格总览
│   │   │   ├── PlanEditorPage.tsx   # 大纲编辑
│   │   │   └── SlideEditorPage.tsx  # 单页编辑
│   │   ├── components/      # 可复用组件
│   │   ├── services/        # API 服务
│   │   │   └── api.ts       # REST API 封装
│   │   └── types/           # TypeScript 类型定义
│   └── package.json
│
└── data/                    # 运行时数据目录
    └── tasks/               # 任务工作空间
```

---

## 🏗️ 架构设计

### 工作流阶段

```
┌─────────────┐    ┌──────────────┐    ┌───────────┐    ┌───────────┐
│  Collecting │ →  │ Editing Plan │ →  │ Designing │ →  │ Completed │
│  收集资料   │    │   编辑大纲   │    │  生成设计  │    │  导出下载  │
└─────────────┘    └──────────────┘    └───────────┘    └───────────┘
      ↑                   ↑                  ↑
   上传文件            AI 规划           并发生成
   输入主题          用户修改          AI 修改助手
```

### 多 Agent 协作

| Agent | 职责 | 提示词 |
|-------|------|--------|
| Collector | 分析上传的文件，提取关键信息 | system_prompt.txt |
| Architect | 规划演示大纲，设计幻灯片结构 | Architect_prompt.md |
| Designer | 生成专业的 HTML 幻灯片 | Designer.md |
| Modifier | 根据用户指令修改幻灯片 | SlideModifier.md |

### 并发生成机制

```python
# 通过 asyncio.Semaphore 控制并发数
self._semaphore = asyncio.Semaphore(max_concurrent)

async def _generate_slide(self, task):
    async with self._semaphore:  # 限制并发数
        await self._call_designer(task)
```

---

## ⚙️ 配置说明

### 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `OPENAI_API_KEY` | OpenAI API 密钥 | (必填) |
| `OPENAI_API_BASE` | API 端点地址 | https://api.openai.com/v1 |
| `OPENAI_MODEL` | 默认模型 | gpt-4o |
| `ARCHITECT_MODEL` | Architect 使用的模型 | gpt-4o |
| `DESIGNER_MODEL` | Designer 使用的模型 | gpt-4o |
| `IMAGE_API_KEY` | 图像生成 API 密钥 | 同 OPENAI_API_KEY |
| `IMAGE_MODEL` | 图像生成模型 | dall-e-3 |
| `MAX_CONCURRENT_SLIDES` | 并发生成幻灯片数 | 3 |
| `SLIDE_GENERATION_TIMEOUT` | 单页生成超时(秒) | 120 |

### 使用第三方 API

```env
# 使用兼容 OpenAI 的第三方 API
OPENAI_API_BASE=https://your-api-endpoint.com/v1
OPENAI_API_KEY=your-api-key

# 使用不同模型
OPENAI_MODEL=claude-3-5-sonnet
DESIGNER_MODEL=gpt-4o-mini
```

---

## 🔌 API 接口

### 核心端点

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/tasks` | 获取任务列表 |
| POST | `/tasks` | 创建新任务 |
| POST | `/tasks/{id}/agent/run` | 启动 AI 生成 |
| GET | `/tasks/{id}/slides/plan` | 获取幻灯片大纲 |
| PUT | `/tasks/{id}/slides/plan` | 更新幻灯片大纲 |
| POST | `/tasks/{id}/slides/generate` | 启动幻灯片生成 |
| GET | `/tasks/{id}/slides/generate/progress` | 获取生成进度 |
| POST | `/tasks/{id}/slides/{index}/ai-modify` | AI 修改幻灯片 |
| GET | `/tasks/{id}/slides/export/{format}` | 导出(html/pptx/zip) |

### WebSocket

```javascript
// 连接 WebSocket 获取实时更新
const ws = new WebSocket(`ws://localhost:8000/tasks/${taskId}/agent/stream`)

ws.onmessage = (event) => {
  const data = JSON.parse(event.data)
  // data.type: 'chunk' | 'tool_call' | 'phase' | 'complete' | 'error'
}
```

---

## 📝 自定义提示词

### 修改 Architect 提示词

编辑 `backend/prompts/Architect_prompt.md`：

```markdown
# 你是一个演示文稿规划专家

## 你的任务
根据用户提供的信息，创建一个结构清晰的演示大纲。

## 输出格式
使用 write_file 工具将规划写入 slides/presentation_plan.json
...
```

### 修改 Designer 提示词

编辑 `backend/prompts/Designer.md`：

```markdown
# Role: Slide Visual Designer

You are an expert presentation designer...

## Design Principles
1. No Scrolling, Full-Screen Design
2. Large Typography, High Contrast
...
```

---

## 🔧 重构说明

### 从原版的改进

| 方面 | 原版 | 重构版 |
|------|------|--------|
| 架构 | 单体脚本 | 模块化分层 |
| 工具系统 | 硬编码 | 可扩展注册表 |
| 配置管理 | 散落各处 | 集中 Settings |
| 状态管理 | 文件依赖 | TaskManager |
| 并发控制 | 顺序执行 | Semaphore 并发 |
| 前端 | 简单页面 | 完整 React SPA |
| 部署 | 手动配置 | Docker 一键启动 |

### 模块职责

- **config/**: 配置单一入口，环境变量 → Pydantic Settings
- **core/**: Agent 核心逻辑，消息处理、工具执行
- **tools/**: 工具模块化，BaseTool 接口 + ToolRegistry 注册
- **workflow/**: 阶段状态机，Phase 枚举 + 状态转换
- **state/**: 任务持久化，CRUD + 状态追踪
- **api/**: RESTful 路由，依赖注入

---

## 📄 许可证

MIT License

---

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！