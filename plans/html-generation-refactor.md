# HTML 生成逻辑重构设计文档

## 概述

将现有的"一次性生成完整HTML"方案重构为"分阶段、并发生成"的新架构，实现：
1. 更好的可控性：每页独立生成和修改
2. 更高的效率：并发请求 LLM 生成多页内容
3. 更灵活的编辑：支持单页修改，无需重新生成全部

### 重要原则

1. **保持现有功能不变** - 本次重构只涉及 HTML 生成部分，不改动项目的其他功能（任务管理、工作区复制等）
2. **复用现有 Agent 架构** - Architect 和 Designer 都是完整的 Agent 实例，复用 `agent_core.py` 中定义的工具能力

---

## 架构设计

### 核心理念：对话历史传递 + 角色切换

整个生成流程是一个**连续的对话**，通过切换系统提示来转换角色：

```
┌─────────────────────────────────────────────────────────────────────┐
│              主 Agent (system_prompt.txt) - 信息收集                 │
├─────────────────────────────────────────────────────────────────────┤
│  使用工具探索项目、分析数据、读取文件                                  │
│  对话历史 (messages) 不断积累                                        │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ 继承对话历史
┌─────────────────────────────────────────────────────────────────────┐
│              Architect (Architect_prompt.md) - 结构规划              │
├─────────────────────────────────────────────────────────────────────┤
│  切换系统提示，但保留完整的对话历史                                    │
│  基于已有上下文，输出 presentation_plan.json                         │
│  (仅在信息不足时才需要额外调用工具)                                   │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ 传递 slide 数据
┌─────────────────────────────────────────────────────────────────────┐
│              Designer (Designer.md) - 内容生成                       │
├─────────────────────────────────────────────────────────────────────┤
│  接收单个 slide 的数据 + theme 信息                                  │
│  生成 HTML 内容                                                     │
│  (仅在需要时才调用工具，如处理图表数据)                               │
└─────────────────────────────────────────────────────────────────────┘
```

**关键设计：对话历史传递**
- 主 Agent 积累的对话历史（所有工具调用结果、分析、理解）传递给 Architect
- Architect 继承完整上下文，无需重新探索项目
- 这样 Architect 可以直接基于已有信息进行结构规划

**Agent 工具能力 (复用 agent_core.py)**
```
┌─────────────────────────────────────────────────────────────────────┐
│  • list_files      - 探索项目结构                                    │
│  • read_file       - 读取源文件、数据文件                             │
│  • execute_command - 运行 Python 脚本处理/分析数据                    │
│  • write_file      - 写入生成的 JSON/HTML 文件                       │
│  • inspect_csv_head - 快速查看 CSV 数据结构                          │
│  • task_completed  - 标记任务完成                                    │
└─────────────────────────────────────────────────────────────────────┘
```

- Architect 和 Designer **可以**使用这些工具，但通常不需要
- 只有在信息不足或需要额外处理时才调用

### 整体流程

```
┌─────────────────────────────────────────────────────────────────────┐
│                       Phase 1: 内容规划                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  【Architect 角色】                                                  │
│    系统提示: 切换为 Architect_prompt.md                              │
│    对话历史: 继承主 Agent 的完整对话历史                              │
│    工具: 可用，但通常不需要（信息已在历史中）                          │
│                                                                     │
│  工作流程:                                                          │
│    1. 分析对话历史中的项目理解和收集的信息                             │
│    2. 根据内容规划幻灯片结构                                          │
│    3. (可选) 如信息不足，调用工具补充                                  │
│    4. write_file - 输出 presentation_plan.json                      │
│                                                                     │
│  输出:                                                              │
│    slides/presentation_plan.json                                    │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     Phase 2: 创建空页框架                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  输入:                                                              │
│    - presentation_plan.json                                         │
│                                                                     │
│  处理 (Python):                                                     │
│    1. 解析 JSON，获取 slides 数组                                    │
│    2. 创建 slides/ 目录                                             │
│    3. 生成 manifest.json (页面元数据)                                │
│    4. 为每个 slide 生成空白 HTML 模板                                 │
│       - 注入 CDN 引用 (Tailwind, Chart.js)                          │
│       - 注入导航脚本                                                 │
│       - 注入 theme 样式变量                                          │
│       - 创建占位符 <div id="content">                               │
│                                                                     │
│  输出:                                                              │
│    slides/                                                          │
│    ├── manifest.json                                                │
│    ├── slide_1.html                                                 │
│    ├── slide_2.html                                                 │
│    └── ...                                                          │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                    Phase 3: 并发生成内容                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  并发控制:                                                          │
│    - 从 .env 读取 SLIDE_GENERATION_CONCURRENCY                      │
│    - 0 或未设置 = 不限制                                             │
│    - 使用 asyncio.Semaphore 控制并发数                               │
│                                                                     │
│  对于每个 slide:                                                    │
│                                                                     │
│  【Designer 角色】                                                   │
│    系统提示: Designer.md + slide 数据 + theme 信息                   │
│    对话历史: 新开对话（不继承主 Agent 历史）                          │
│    工具: 可用，仅在需要时调用                                         │
│                                                                     │
│    工作流程:                                                        │
│      1. 接收 slide JSON 数据和 theme 信息                            │
│      2. 直接根据数据生成 HTML 内容                                    │
│      3. (可选) 如需处理图表数据，调用 execute_command                  │
│      4. write_file - 更新 slide_X.html                              │
│                                                                     │
│    失败处理:                                                        │
│      - 指数退避重试 (最多 3 次)                                       │
│      - 连续 3 次失败后询问用户                                        │
│                                                                     │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                │
│   │ Designer    │  │ Designer    │  │ Designer    │  ...           │
│   │  Agent #1   │  │  Agent #2   │  │  Agent #3   │                │
│   │  (slide_1)  │  │  (slide_2)  │  │  (slide_3)  │                │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                │
│          ↓                ↓                ↓                        │
│   slide_1.html     slide_2.html     slide_3.html                   │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│                     Phase 4: 导出合并 (可选)                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  输入:                                                              │
│    - slides/ 目录下的所有 slide_*.html                               │
│    - manifest.json (获取顺序)                                        │
│                                                                     │
│  处理:                                                              │
│    1. 按顺序读取每个 HTML 文件                                       │
│    2. 提取 <div id="content"> 内部内容                              │
│    3. 包装成 <section class="slide">...</section>                   │
│    4. 合并到单一 HTML 文件                                           │
│    5. 注入统一的导航脚本 (visibility 切换)                           │
│                                                                     │
│  输出:                                                              │
│    exported/presentation.html                                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 数据结构定义

### 1. Architect JSON (presentation_plan.json)

```json
{
  "theme": {
    "color_palette": "Modern Blue - Clean professional look",
    "background_class": "bg-slate-900",
    "text_primary": "text-white",
    "text_accent": "text-blue-400",
    "font_family": "Inter, sans-serif"
  },
  "slides": [
    {
      "id": "slide_1",
      "type": "title",
      "title": "Q3 2024 Financial Report",
      "subtitle": "Performance Overview and Strategic Outlook",
      "content_points": [],
      "chart_data": null,
      "chart_instruction": null,
      "speaker_notes": "Welcome everyone to our Q3 review..."
    },
    {
      "id": "slide_2",
      "type": "section_header",
      "title": "Executive Summary",
      "subtitle": null,
      "content_points": [],
      "chart_data": null,
      "chart_instruction": null,
      "speaker_notes": null
    },
    {
      "id": "slide_3",
      "type": "bullet_list",
      "title": "Key Highlights",
      "subtitle": null,
      "content_points": [
        "Revenue increased 25% YoY",
        "Expanded to 3 new markets",
        "Customer satisfaction at 94%"
      ],
      "chart_data": null,
      "chart_instruction": null,
      "speaker_notes": null
    },
    {
      "id": "slide_4",
      "type": "split_content_chart",
      "title": "Revenue Growth Trend",
      "subtitle": null,
      "content_points": [
        "Consistent growth across all segments",
        "Q3 marked strongest quarter"
      ],
      "chart_data": {
        "type": "line",
        "labels": ["Q1", "Q2", "Q3", "Q4"],
        "datasets": [
          {
            "label": "Revenue (M)",
            "data": [10, 15, 22, null]
          }
        ]
      },
      "chart_instruction": "Line chart showing quarterly revenue growth",
      "speaker_notes": null
    },
    {
      "id": "slide_5",
      "type": "big_stat",
      "title": "Total Revenue",
      "subtitle": null,
      "content_points": [],
      "stat_value": "$47M",
      "stat_context": "25% increase from last year",
      "chart_data": null,
      "chart_instruction": null,
      "speaker_notes": null
    },
    {
      "id": "slide_6",
      "type": "grid_cards",
      "title": "Key Metrics",
      "subtitle": null,
      "content_points": [],
      "cards": [
        {"title": "Revenue", "value": "$47M", "change": "+25%"},
        {"title": "Users", "value": "2.3M", "change": "+18%"},
        {"title": "NPS", "value": "72", "change": "+5"},
        {"title": "Churn", "value": "2.1%", "change": "-0.3%"}
      ],
      "chart_data": null,
      "chart_instruction": null,
      "speaker_notes": null
    }
  ]
}
```

### 2. Slide Types 枚举

| Type | 描述 | 必需字段 |
|------|------|----------|
| `title` | 标题页 | title, subtitle |
| `section_header` | 章节过渡页 | title |
| `bullet_list` | 要点列表 | title, content_points |
| `split_content_chart` | 左文字右图表 | title, content_points, chart_instruction |
| `big_stat` | 大数字展示 | title, stat_value, stat_context |
| `grid_cards` | 网格卡片 | title, cards |

### 3. manifest.json

```json
{
  "version": "1.0",
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-15T11:45:00Z",
  "theme": {
    "background_class": "bg-slate-900",
    "text_primary": "text-white",
    "text_accent": "text-blue-400"
  },
  "slides": [
    {
      "id": "slide_1",
      "file": "slide_1.html",
      "type": "title",
      "title": "Q3 2024 Financial Report",
      "status": "completed",
      "generated_at": "2024-01-15T10:31:00Z"
    },
    {
      "id": "slide_2",
      "file": "slide_2.html",
      "type": "section_header",
      "title": "Executive Summary",
      "status": "completed",
      "generated_at": "2024-01-15T10:31:05Z"
    },
    {
      "id": "slide_3",
      "file": "slide_3.html",
      "type": "bullet_list",
      "title": "Key Highlights",
      "status": "pending",
      "generated_at": null
    }
  ],
  "total_slides": 6,
  "completed_slides": 2
}
```

**Status 枚举:**
- `pending`: 空页，等待生成
- `generating`: 正在生成中
- `completed`: 生成完成
- `failed`: 生成失败
- `modified`: 用户手动修改过

---

## 空白 HTML 模板

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Slide {{SLIDE_INDEX}} - {{SLIDE_TITLE}}</title>
    
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    
    <!-- Theme Variables -->
    <style>
        :root {
            --bg-primary: {{THEME_BG}};
            --text-primary: {{THEME_TEXT}};
            --text-accent: {{THEME_ACCENT}};
        }
        
        html, body {
            margin: 0;
            padding: 0;
            width: 100vw;
            height: 100vh;
            overflow: hidden;
        }
        
        .slide-container {
            width: 100%;
            height: 100%;
        }
    </style>
</head>
<body class="{{THEME_BG_CLASS}}">
    <!-- Navigation Indicator -->
    <div class="fixed bottom-4 right-4 text-sm opacity-50 {{THEME_TEXT_CLASS}}">
        {{SLIDE_INDEX}} / {{TOTAL_SLIDES}}
    </div>
    
    <!-- Slide Content Container -->
    <div id="content" class="slide-container">
        <!-- Content will be injected here -->
        <div class="h-full flex items-center justify-center {{THEME_TEXT_CLASS}}">
            <div class="text-center">
                <div class="text-6xl mb-4">⏳</div>
                <div class="text-2xl">正在生成内容...</div>
            </div>
        </div>
    </div>
    
    <!-- Navigation Script -->
    <script>
        const SLIDE_CONFIG = {
            currentIndex: {{SLIDE_INDEX}},
            totalSlides: {{TOTAL_SLIDES}},
            prevSlide: {{PREV_SLIDE_PATH}},
            nextSlide: {{NEXT_SLIDE_PATH}}
        };
        
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft' && SLIDE_CONFIG.prevSlide) {
                window.location.href = SLIDE_CONFIG.prevSlide;
            } else if ((e.key === 'ArrowRight' || e.key === ' ' || e.key === 'Enter') && SLIDE_CONFIG.nextSlide) {
                window.location.href = SLIDE_CONFIG.nextSlide;
            }
        });
    </script>
</body>
</html>
```

---

## 核心类设计

### SlideGenerator 类

```python
class SlideGenerator:
    """
    负责整个幻灯片生成流程的核心类
    
    关键设计：复用 agent_core.Agent 类，通过不同的系统提示
    创建 Architect Agent 和 Designer Agent
    """
    
    def __init__(
        self,
        api_key: str,
        workspace_dir: str,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
        concurrency: int = 0,  # 0 = 不限制
        on_slide_progress: Optional[Callable] = None
    ):
        self.api_key = api_key
        self.workspace_dir = workspace_dir
        self.model = model
        self.base_url = base_url
        self.concurrency = concurrency
        self.on_slide_progress = on_slide_progress
        
        # 加载 prompt 模板
        self.architect_prompt = self._load_prompt("Architect_prompt.md")
        self.designer_prompt = self._load_prompt("Designer.md")
    
    def switch_to_architect(self, agent: Agent) -> None:
        """
        将现有 Agent 切换为 Architect 角色
        
        关键：保留对话历史，只切换系统提示
        """
        agent.system_prompt = self._build_architect_system_prompt()
    
    def _build_architect_system_prompt(self) -> str:
        """
        构建 Architect 的系统提示
        包含 Architect_prompt.md + 工具定义
        """
        tool_definitions = agent.tools.get_tool_definitions_json()
        return f"{self.architect_prompt}\n\n{tool_definitions}"
    
    def _create_designer_agent(self, slide_data: dict, theme: dict) -> Agent:
        """
        创建新的 Designer Agent 实例
        
        Designer 不继承主 Agent 的对话历史，因为它只需要处理单个 slide
        """
        prompt = self._build_designer_prompt(slide_data, theme)
        return Agent(
            api_key=self.api_key,
            workspace_dir=self.workspace_dir,
            model=self.model,
            base_url=self.base_url,
            system_prompt_override=prompt
        )
    
    # Phase 1: 规划
    async def generate_plan(
        self,
        agent: Agent,  # 传入已有的 Agent（带对话历史）
        user_request: str
    ) -> dict:
        """
        切换 Agent 为 Architect 角色，生成 presentation_plan.json
        
        关键设计：
        - 传入已有的 Agent 实例（带有完整的对话历史）
        - 切换系统提示为 Architect_prompt.md
        - Architect 可以看到之前所有的工具调用结果和分析
        - 基于这些信息直接输出结构化的规划
        """
        # 切换为 Architect 角色
        self.switch_to_architect(agent)
        
        # 构建任务指令
        task = f"""
基于你之前收集的所有信息，现在请为用户创建演示文稿规划。

用户请求：{user_request}

请根据之前的分析结果，直接输出 presentation_plan.json。
如果你需要更多信息，可以使用工具进行补充。

输出文件路径：slides/presentation_plan.json
"""
        
        # 运行 Agent（会继续之前的对话）
        result = await self._run_agent_async(agent, task)
        
        # 读取并返回生成的 plan
        plan_path = Path(self.workspace_dir) / "slides" / "presentation_plan.json"
        return json.loads(plan_path.read_text())
    
    # Phase 2: 创建框架
    def create_slide_framework(
        self,
        plan: dict,
        output_dir: str = "slides"
    ) -> Path:
        """
        根据 plan 创建空白 HTML 模板和 manifest.json
        """
        ...
    
    # Phase 3: 并发生成
    async def generate_all_slides(
        self,
        plan: dict,
        slides_dir: Path
    ) -> dict:
        """
        并发生成所有幻灯片内容
        返回生成结果统计
        """
        ...
    
    async def generate_single_slide(
        self,
        slide_data: dict,
        theme: dict,
        output_path: Path
    ) -> bool:
        """
        使用 Designer 生成单个幻灯片的内容
        
        Designer 是一个新的 Agent 实例（不继承主 Agent 历史）
        因为每个 slide 的生成是独立的，不需要之前的上下文
        
        包含指数退避重试逻辑
        """
        designer = self._create_designer_agent(slide_data, theme)
        
        # Designer 的任务指令更简洁，因为所有信息都在 prompt 中
        task = f"""
请为这个幻灯片生成 HTML 内容。

slide 数据和 theme 信息已在系统提示中提供。

如果需要处理图表数据，可以使用 execute_command 运行 Python。

使用 write_file 将生成的 HTML 内容写入：{output_path}
只需要写入 <div id="content"> 的内部内容，不需要完整的 HTML 框架。
"""
        
        return await self._run_with_retry(designer, task)
    
    # Phase 4: 导出
    def export_to_single_file(
        self,
        slides_dir: Path,
        output_path: Path
    ) -> Path:
        """
        将多个 HTML 文件合并为单一演示文稿
        """
        ...
    
    # 单页修改
    async def regenerate_slide(
        self,
        slide_id: str,
        slides_dir: Path,
        user_feedback: Optional[str] = None
    ) -> bool:
        """
        重新生成指定幻灯片
        可以带上用户反馈
        """
        ...
```

### 重试机制

```python
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0  # 秒
    max_delay: float = 30.0
    exponential_base: float = 2.0

async def with_retry(
    func: Callable,
    config: RetryConfig,
    on_failure: Optional[Callable] = None
) -> Any:
    """
    指数退避重试包装器
    
    重试间隔: base_delay * (exponential_base ** attempt)
    - 第1次重试: 1秒后
    - 第2次重试: 2秒后
    - 第3次重试: 4秒后
    """
    for attempt in range(config.max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == config.max_retries - 1:
                if on_failure:
                    return on_failure(e)
                raise
            
            delay = min(
                config.base_delay * (config.exponential_base ** attempt),
                config.max_delay
            )
            await asyncio.sleep(delay)
```

---

## 环境变量配置

在 `.env.example` 中添加：

```env
# Slide Generation Settings
SLIDE_GENERATION_CONCURRENCY=3   # 并发生成数量，0表示不限制
SLIDE_GENERATION_TIMEOUT=120     # 单个slide生成超时（秒）
```

---

## UI 更新

### app.py 修改点

1. **新增生成模式切换**
   - "传统模式"：一次性生成完整 HTML（保留兼容）
   - "分步模式"：使用新的 SlideGenerator 流程

2. **进度显示**
   - 显示当前生成阶段（规划中 / 创建框架 / 生成内容）
   - 显示每个 slide 的生成状态（pending / generating / completed / failed）
   - 进度条显示已完成百分比

3. **失败处理 UI**
   - 连续 3 次失败后弹出对话框
   - 选项：重试 / 跳过此页（保留空白）/ 停止生成

4. **预览更新**
   - 支持在 slides/ 目录下的多文件预览
   - 提供 iframe 预览单个 slide
   - "导出"按钮触发合并

5. **单页修改**
   - 点击某一页后显示"修改此页"按钮
   - 输入修改请求，触发 regenerate_slide

---

## 文件变更清单

| 文件 | 操作 | 描述 |
|------|------|------|
| `slide_generator.py` | 新建 | SlideGenerator 类及辅助函数 |
| `templates/slide_template.html` | 新建 | 空白 slide HTML 模板 |
| `app.py` | 修改 | 添加新的生成流程 UI（仅 HTML 生成部分） |
| `agent_core.py` | 修改 | 添加 `system_prompt_override` 参数支持 |
| `.env.example` | 修改 | 添加并发配置 |
| `Architect_prompt.md` | 修改 | 完善 JSON Schema 说明，明确工具使用流程 |
| `Designer.md` | 修改 | 添加输入格式说明，明确工具使用流程 |

### agent_core.py 修改说明

需要在 `Agent.__init__()` 中添加 `system_prompt_override` 参数：

```python
def __init__(
    self,
    api_key: str,
    workspace_dir: str,
    system_prompt_path: str = "system_prompt.txt",
    model: str = "gpt-4o",
    base_url: Optional[str] = None,
    on_tool_call: Optional[Callable[[ToolCallInfo], None]] = None,
    on_message: Optional[Callable[[str, str], None]] = None,
    enable_thinking: Optional[bool] = None,
    system_prompt_override: Optional[str] = None  # 新增参数
):
    ...
    # 加载系统提示
    if system_prompt_override:
        base_prompt = system_prompt_override
    else:
        base_prompt = self._load_system_prompt(system_prompt_path)
    ...
```

---

## 实施步骤

### 阶段 1: 基础设施
1. 创建 `slide_generator.py` 基础结构
2. 实现 Architect JSON 解析和验证
3. 实现空白 HTML 模板生成
4. 实现 manifest.json 管理

### 阶段 2: 核心生成逻辑
1. 实现 generate_plan（调用 Architect LLM）
2. 实现 generate_single_slide（调用 Designer LLM）
3. 实现并发控制（asyncio.Semaphore）
4. 实现指数退避重试

### 阶段 3: 导出和修改
1. 实现 export_to_single_file（合并 HTML）
2. 实现 regenerate_slide（单页修改）

### 阶段 4: UI 集成
1. 更新 app.py 添加新生成模式
2. 添加进度显示
3. 添加失败处理 UI
4. 更新预览面板

### 阶段 5: 测试和优化
1. 单元测试
2. 集成测试
3. 性能优化
4. 错误处理完善

---

## 风险和考虑

1. **API Rate Limit**
   - 通过并发限制缓解
   - 考虑添加请求队列

2. **生成内容不一致**
   - 每个 slide 独立生成，可能风格略有差异
   - 通过在 prompt 中强调 theme 信息缓解
   - Designer Agent 可以读取已生成的 slides 作为参考

3. **大型演示文稿**
   - 超过 20 页可能需要较长时间
   - 考虑添加分批生成选项

4. **浏览器兼容性**
   - 多文件导航依赖 window.location
   - 确保导出的单文件在所有浏览器正常工作

5. **Agent 工具调用开销**
   - 每个 Designer Agent 可能会进行多次工具调用
   - 需要平衡"工具能力"和"生成速度"
   - 可以在 Designer prompt 中指导何时使用/不使用工具

---

## 与现有功能的关系

本次重构**仅涉及 HTML 生成逻辑**，以下功能保持不变：

- ✅ 任务管理 (`task_manager.py`)
- ✅ 工作区复制 (`workspace_copier.py`)
- ✅ 目录选择 (`directory_picker.py`)
- ✅ Streamlit UI 框架 (`app.py` 的任务列表、设置面板等)
- ✅ Agent 核心工具 (`agent_core.py` 的 AgentTools 类)

修改点集中在：
- `app.py` 中"发送消息"后的处理逻辑
- 新增 `slide_generator.py` 作为生成流程的协调器
- `agent_core.py` 添加 `system_prompt_override` 参数