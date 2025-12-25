# 🎨 AI Presentation Agent

一个基于 AI 的自动化演示文稿生成工具，使用 Streamlit 构建交互界面，支持通过自然语言对话创建数据驱动的 HTML 演示文稿。

## ✨ 功能特性

- **🤖 AI 驱动**: 使用 OpenAI 兼容的 API（支持 GPT-4、Claude 等模型）自动生成演示文稿
- **💬 对话式交互**: 通过自然语言描述需求，AI 自动理解并执行
- **📊 数据驱动**: 支持读取 CSV、JSON 等数据文件，自动生成可视化图表
- **🖼️ 实时预览**: 右侧面板实时显示生成的 HTML 演示文稿
- **📋 多任务管理**: 支持创建、切换、删除多个任务，每个任务独立管理
- **📁 工作目录隔离**: 每个任务有独立的工作目录，文件互不干扰
- **🔄 流式输出**: 支持实时显示 AI 生成过程
- **✏️ 幻灯片修改**: 支持针对单页幻灯片进行精细化修改

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
2. 选择一个包含数据文件的工作目录
3. 确认创建任务

### 2. 与 AI 对话

在聊天输入框中描述你的需求，例如：

- "请分析 data.csv 文件，创建一个销售数据可视化演示文稿"
- "添加一页关于年度趋势的图表"
- "修改第 3 页的配色方案为蓝色系"

### 3. 查看和修改

- 右侧面板实时显示生成的 HTML 预览
- 使用「✏️ 修改当前幻灯片」功能针对特定页面进行调整
- 点击「🔄 刷新预览」更新显示

## 📁 项目结构

```
auto_presentation/
├── app.py              # Streamlit 主应用
├── agent_core.py       # AI Agent 核心逻辑
├── task_manager.py     # 任务管理模块
├── workspace_copier.py # 工作目录复制工具
├── directory_picker.py # 目录选择器
├── system_prompt.txt   # AI 系统提示词
├── design_spec.md      # 设计规范文档
├── requirements.txt    # Python 依赖
├── .env.example        # 环境变量示例
├── .env               # 环境变量配置（需创建）
├── run.bat            # Windows 启动脚本
├── plans/             # 设计文档
└── tasks/             # 任务工作目录（自动创建）
```

## 🛠️ 技术栈

- **前端框架**: [Streamlit](https://streamlit.io/)
- **AI 接口**: [OpenAI API](https://platform.openai.com/)（兼容 Claude、Gemini 等）
- **HTML 解析**: BeautifulSoup4
- **数据处理**: Pandas
- **图表库**: Chart.js, Tailwind CSS（在生成的 HTML 中使用）

## 🔧 工具能力

AI Agent 具备以下工具能力：

| 工具 | 功能 |
|------|------|
| `list_files` | 列出目录下的文件和文件夹 |
| `read_file` | 读取文件内容 |
| `write_file` | 写入/创建文件 |
| `execute_command` | 执行系统命令 |
| `inspect_csv_head` | 查看 CSV 文件结构和前几行数据 |
| `task_completed` | 标记任务完成 |

## 📝 注意事项

1. **API 费用**: 使用 OpenAI API 会产生费用，请注意控制使用量
2. **文件安全**: Agent 只能访问任务工作目录内的文件
3. **网络要求**: 需要能够访问配置的 API 端点
4. **浏览器兼容**: 推荐使用 Chrome、Firefox 或 Edge 最新版本

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License