# 🎨 AI Presentation Agent

一个基于多 Agent 架构的自动化演示文稿生成工具，使用 Streamlit 构建交互界面，支持通过自然语言对话创建数据驱动的 HTML 演示文稿。

## ✨ 功能特性

- **🤖 多 Agent 架构**: 采用 Collector → Architect → Designer 三阶段工作流
- **💬 对话式交互**: 通过自然语言描述需求，AI 自动理解并执行
- **📊 数据驱动**: 支持读取 CSV、JSON 等数据文件，自动生成可视化图表
- **🖼️ AI 图片生成**: Designer Agent 支持使用 AI 生成自定义图片
- **📋 多任务管理**: 支持创建、切换、删除多个任务，每个任务独立管理
- **📁 工作目录隔离**: 每个任务有独立的工作目录，文件互不干扰
- **🔄 流式输出**: 支持实时显示 AI 生成过程
- **⚡ 并发生成**: 多页幻灯片并发生成，大幅提升效率
- **📊 网格视图**: 实时监控幻灯片生成状态，支持单页编辑
- **✏️ 规划编辑器**: 可在生成前编辑演示文稿规划 JSON

## 🏗️ 系统架构

### 多 Agent 工作流

```
用户输入 → [Collector Agent] → [Architect Agent] → [Designer Agents] → HTML 幻灯片
              ↓                     ↓                    ↓
          探索项目              规划结构              并发生成
          收集信息          presentation_plan.json    单页HTML
```

1. **Collector Agent**: 探索项目结构，读取文件，收集创建演示文稿所需的所有信息
2. **Architect Agent**: 分析收集的信息，规划幻灯片结构，生成 `presentation_plan.json`
3. **Designer Agents**: 根据规划并发生成每页幻灯片的 HTML 内容

### Agent 工具能力

| 工具 | 功能 | 可用 Agent |
|------|------|------------|
| `list_files` | 列出目录下的文件和文件夹 | 全部 |
| `read_file` | 读取文件内容（带行号，自动截断大文件） | 全部 |
| `write_file` | 写入/创建文件 | 全部 |
| `execute_command` | 执行系统命令 | 全部 |
| `inspect_csv_head` | 快速预览 CSV 文件结构 | 全部 |
| `task_completed` | 标记任务完成 | 全部 |
| `phase_complete` | 标记阶段完成，触发工作流转换 | Collector, Architect |
| `generate_image` | 使用 AI 生成图片 | 仅 Designer |

### 工具调用格式

本项目使用 **JSON 边界标记** 格式进行工具调用，而非 OpenAI 原生 function calling：

```
<<<TOOL_CALL>>>
{"tool": "tool_name", "parameters": {...}}
<<<END_TOOL_CALL>>>
```

这种格式与各种 API 代理和不同提供商更加兼容。

## 📦 安装

### 1. 克隆项目

```bash
git clone <repository-url>
cd auto_presentation
```

### 2. 创建虚拟环境（推荐）

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/Mac
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

## ⚙️ 配置

### 1. 创建环境变量文件

复制示例配置文件：

```bash
cp .env.example .env
```

### 2. 编辑 `.env` 文件

```env
# OpenAI API 配置
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o

# 图片生成 API（可选，用于 Designer 的 generate_image 工具）
IMAGE_API_KEY=your-image-api-key
IMAGE_API_BASE_URL=https://api.openai.com/v1
IMAGE_MODEL=dall-e-3

# 幻灯片生成配置（可选）
SLIDE_GENERATION_CONCURRENCY=0  # 0 = 无限制并发
SLIDE_GENERATION_TIMEOUT=120    # 单页超时时间（秒）

# 如果使用兼容 OpenAI 的其他服务（如 Azure、Claude API 代理等）
# OPENAI_BASE_URL=https://your-proxy-url/v1
# OPENAI_MODEL=claude-3-5-sonnet-20241022
```

## 🚀 使用方法

### Windows 用户

双击 `run.bat` 即可启动，程序会自动打开浏览器。

### 命令行启动

```bash
streamlit run app.py
```

然后在浏览器中访问 `http://localhost:8501`

## 📖 使用指南

### 1. 创建新任务

1. 点击左侧边栏的「➕ 新建任务」按钮
2. 选择一个包含数据文件的工作目录（或选择特定文件）
3. 确认创建任务

### 2. 与 AI 对话

在聊天输入框中描述你的需求，例如：

- "请分析 data.csv 文件，创建一个销售数据可视化演示文稿"
- "根据这个项目创建一个技术介绍 PPT"
- "请用中文创建 8 页的项目汇报幻灯片"

### 3. 工作流程

1. **信息收集**: Collector Agent 自动探索项目、分析数据
2. **规划编辑**: Architect Agent 生成规划后，可在编辑器中修改
3. **幻灯片生成**: 确认规划后，Designer Agents 并发生成各页
4. **网格监控**: 实时查看生成进度，支持单页预览和编辑
5. **导出**: 完成后可导出为单个 HTML 文件

### 4. 修改幻灯片

- 在网格视图中点击任意幻灯片的「🔍 查看/编辑」按钮
- 在右侧输入修改请求，如"将标题改为红色"、"添加一个柱状图"
- Designer Agent 会根据你的描述重新生成该页

## 📁 项目结构

```
auto_presentation/
├── app.py                  # Streamlit 主应用
├── agent_core.py           # AI Agent 核心逻辑（工具定义、工具执行、对话管理）
├── slide_generator.py      # 幻灯片生成器（并发生成、框架创建、导出）
├── task_manager.py         # 任务管理模块
├── workspace_copier.py     # 工作目录复制工具
├── directory_picker.py     # 目录/文件选择器
├── gen_image.py            # AI 图片生成模块
├── speech_generator.py     # 演讲稿生成模块
├── system_prompt.txt       # Collector Agent 系统提示词
├── Architect_prompt.md     # Architect Agent 系统提示词
├── Designer.md             # Designer Agent 系统提示词
├── design_spec.md          # 设计规范文档
├── requirements.txt        # Python 依赖
├── .env.example            # 环境变量示例
├── .env                    # 环境变量配置（需创建）
├── run.bat                 # Windows 启动脚本
├── plans/                  # 设计文档
├── front_end/              # 前端相关文件（备用）
├── test_slides/            # 测试幻灯片
└── tasks/                  # 任务工作目录（自动创建）
```

## 🛠️ 技术栈

- **前端框架**: [Streamlit](https://streamlit.io/)
- **AI 接口**: [OpenAI API](https://platform.openai.com/)（兼容 Claude、Gemini 等）
- **工具调用**: JSON 边界标记格式（自定义实现）
- **HTML 解析**: BeautifulSoup4
- **数据处理**: Pandas
- **幻灯片技术**: 
  - [Tailwind CSS](https://tailwindcss.com/) - 样式
  - [Chart.js](https://www.chartjs.org/) - 数据可视化

## 🎨 幻灯片设计规范

生成的幻灯片遵循以下设计原则：

- **全屏设计**: 每页占满视口，无滚动
- **大字体**: 投影友好的字号，高对比度
- **信息密集**: 充分展示数据，合理组织布局
- **专业风格**: 参考 Apple Keynote 和 McKinsey 咨询风格
- **数据可视化**: 使用 Chart.js Canvas 绑定图表（禁止 SVG/Mermaid）

详见 [Designer.md](Designer.md) 设计规范文档。

## 📝 注意事项

1. **API 费用**: 使用 OpenAI API 会产生费用，请注意控制使用量
2. **文件安全**: Agent 只能访问任务工作目录内的文件
3. **网络要求**: 需要能够访问配置的 API 端点
4. **浏览器兼容**: 推荐使用 Chrome、Firefox 或 Edge 最新版本
5. **大文件处理**: 
   - 数据文件（CSV、JSON 等）自动截断到 50 行
   - 其他文本文件截断到 500 行
   - 建议使用 Python 脚本处理大数据

## 🔧 高级配置

### 并发控制

通过环境变量控制幻灯片生成并发数：

```env
SLIDE_GENERATION_CONCURRENCY=3  # 最多同时生成 3 页
```

设为 0 表示不限制并发（默认）。

### 超时设置

```env
SLIDE_GENERATION_TIMEOUT=180  # 单页生成超时 180 秒
```

### 模型选择

支持任何 OpenAI 兼容的 API，包括：
- OpenAI GPT-4o, GPT-4-turbo
- Anthropic Claude (通过代理)
- Azure OpenAI
- 本地模型 (通过兼容 API)

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License