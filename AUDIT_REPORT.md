# 重构版代码审阅报告

## 概述

本报告对比原版 (Streamlit-based) 和重构版 (FastAPI + React) 的代码实现，检查全流程是否完整。

**审阅日期**: 2025-12-30

## 工作流程对比

原版工作流程:
1. 选择文件/目录 → 复制到工作区
2. 输入想法 → Architect Agent 生成 `presentation_plan.json`
3. 用户审阅/编辑计划
4. 并发生成每一页 HTML (Designer Agent)
5. 单独编辑/重生成幻灯片
6. 导出为 HTML/PPTX/ZIP

---

## 第一步：文件选择/上传 ⚠️ 部分实现

### 后端 (refactor_version/backend)

| 文件 | 状态 | 说明 |
|------|------|------|
| `api/upload.py` | ✅ 存在 | 有上传端点 |
| `api/tasks.py` | ✅ 存在 | 任务 CRUD |

### 前端 (refactor_version/frontend)

| 文件 | 状态 | 问题 |
|------|------|------|
| `TaskListPage.tsx` | ⚠️ 部分 | 有 `handleFileUpload` 但只处理简单上传，缺少目录选择 |
| `services/api.ts` | ⚠️ 部分 | `uploadFiles` 函数存在但未使用 |

### 问题

1. **缺少目录选择器**: 原版有 `directory_picker.py` 使用 tkinter 选择目录，重构版缺失
2. **缺少文件复制逻辑**: 原版有 `workspace_copier.py` 扫描和复制文件，重构版缺失

---

## 第二步：PPT 框架生成 (Architect Phase) ⚠️ 刚修复

### 后端

| 文件 | 状态 | 说明 |
|------|------|------|
| `api/agent.py` | ✅ 刚添加 | 启动 Agent 生成流程 |
| `core/agent.py` | ✅ 存在 | Agent 类实现 |
| `prompts/Architect_prompt.md` | ✅ 存在 | Architect 系统提示 |

### 前端

| 文件 | 状态 | 问题 |
|------|------|------|
| `TaskListPage.tsx` | ✅ 刚修复 | `handleGenerate` 调用 `runAgent` API |
| `services/api.ts` | ✅ 刚添加 | `runAgent`, `getAgentStatus` 函数 |

### 问题

1. ✅ **已修复**: 之前 `submitIdea` 只保存 metadata 不触发 LLM
2. ⚠️ **待验证**: Agent 是否能正确生成 `presentation_plan.json`

---

## 第三步：计划编辑 (Plan Editor) ⚠️ 有问题

### 后端

| 文件 | 状态 | 说明 |
|------|------|------|
| `api/slides.py` | ✅ 存在 | `get_plan`, `update_plan` 端点存在 |

### 前端

| 文件 | 状态 | 问题 |
|------|------|------|
| `PlanEditorPage.tsx` | ⚠️ 有问题 | 见下方分析 |

### PlanEditorPage.tsx 问题分析

```typescript
// 第 94-108 行: handleGenerate 调用 generatePlan
const handleGenerate = async () => {
  if (!prompt || !taskId) return
  setIsGenerating(true)
  try {
    const result = await generatePlan(taskId, prompt)  // ❌ 这个 API 不存在！
    setPresentation(result)
    // ...
  }
}
```

**问题**:
- `generatePlan(taskId, prompt)` 在 `api.ts` 中定义了，但后端**没有对应端点**
- 应该复用新添加的 `runAgent` API，而不是调用不存在的 `generatePlan`

---

## 第四步：并发 Slide 生成 (Designer Phase) ❌ 严重问题

### 后端

| 文件 | 状态 | 问题 |
|------|------|------|
| `api/slides.py` | ❌ 断开 | `start_generation` 端点存在但逻辑不完整 |
| `workflow/slide_generator.py` | ✅ 存在 | `SlideGenerator` 类存在 |

### api/slides.py 问题分析

```python
# 第 85-109 行: start_generation 端点
@router.post("/{task_id}/slides/generate")
async def start_generation(task_id: str, background_tasks: BackgroundTasks):
    # ...
    manifest = manifest_manager.load_from_plan()  # ❌ 问题1: 期望特定 JSON 格式
    
    background_tasks.add_task(
        generator.generate_all,  # ⚠️ 问题2: generate_all 是否正确实现?
        manifest
    )
```

**问题 1**: `load_from_plan()` 期望的 JSON 格式可能与 Architect 生成的不匹配

```python
# manifest.py 第 42-57 行
def load_from_plan(self, plan_path: Path = None) -> SlideManifest:
    # 期望格式:
    # {
    #   "title": "...",
    #   "slides": [{"id": "...", "title": "...", "content": "..."}]
    # }
```

**问题 2**: `SlideGenerator.generate_all()` 的实现需要验证

### 前端

| 文件 | 状态 | 问题 |
|------|------|------|
| `GenerationPage.tsx` | ❌ 有 Mock 数据 | 使用假数据，未正确连接后端 |

### GenerationPage.tsx 问题分析

```typescript
// 第 14-17 行: MOCK 数据!
const initialSlides: SlideGenerationStatus[] = [
  { id: "1", title: "标题页", section: "开始", status: "done", progress: 100 },
  { id: "2", title: "目录", section: "结构", status: "done", progress: 100 },
]

// 第 37-51 行: 假的进度更新!
useEffect(() => {
  const interval = setInterval(() => {
    setSlides(prev => prev.map(s => {
      if (s.status === 'running') {
        const next = s.progress + Math.random() * 7  // ❌ 假进度!
        // ...
      }
    }))
  }, 1400)
}, [])
```

**问题**:
1. 页面初始化使用**硬编码的假数据**，而不是从后端获取
2. 进度更新是**假的随机数**，不是真实生成进度
3. `getGenerationProgress(taskId)` 可能返回空，所以回退到假数据

---

## 第五步：单独 Slide 编辑 ❌ 严重问题

### 后端

| 文件 | 状态 | 问题 |
|------|------|------|
| `api/slides.py` | ⚠️ 存在 | `update_slide`, `regenerate_slide`, `modify_slide_with_ai` 端点存在 |

### 前端

| 文件 | 状态 | 问题 |
|------|------|------|
| `SlideEditorPage.tsx` | ❌ 完全是 Mock | 未连接后端 |

### SlideEditorPage.tsx 问题分析

```typescript
// 第 8-19 行: 完全是 MOCK 数据!
const INITIAL_SLIDES: DetailedSlide[] = [
  {
    id: 's1',
    title: 'AI 幻灯片助手',
    subtitle: '幻灯片生成与编辑系统',
    layout: 'standard',
    content: [
      { id: 'c1', label: '核心功能', value: '...' },
      { id: 'c2', label: '设计理念', value: '...' }
    ]
  }
]

// 第 41-49 行: loadData 没有加载真实 slides!
const loadData = async () => {
  try {
    const task = await getTask(taskId!)
    setTaskName(task.name)
    // ❌ TODO 注释: "Load slides data here" - 没有实现!
  } catch (error) {
    console.error('Failed to load data:', error)
  }
}
```

**问题**:
1. `loadData()` **没有加载实际的幻灯片数据**
2. 使用硬编码的 `INITIAL_SLIDES` 而不是从后端获取
3. `handleApplyAI()` 调用 `modifySlideWithAI` 但可能无法工作

---

## 第六步：导出 HTML/PPTX ⚠️ 部分实现

### 后端

| 文件 | 状态 | 说明 |
|------|------|------|
| `export/html_exporter.py` | ✅ 存在 | HTMLExporter 类 |
| `export/pptx_exporter.py` | ✅ 存在 | PPTXExporter 类 (使用 Playwright) |
| `export/zip_exporter.py` | ✅ 存在 | ZIPExporter 类 |
| `api/slides.py` | ⚠️ 端点存在 | `export_html`, `export_pptx`, `export_zip` |

### 前端

| 文件 | 状态 | 说明 |
|------|------|------|
| `GenerationPage.tsx` | ⚠️ 有按钮 | `handleExport` 调用 `getExportUrl` |
| `services/api.ts` | ✅ 存在 | `getExportUrl(taskId, format)` |

### 问题

1. 导出功能需要先有成功生成的 slides 才能工作
2. 由于 slide 生成有问题，导出无法测试

---

## 总结

### 完整性评估

| 阶段 | 原版状态 | 重构版状态 | 完成度 |
|------|----------|------------|--------|
| 1. 文件上传 | ✅ 完整 | ⚠️ 基础功能 | 50% |
| 2. Architect 生成 | ✅ 完整 | ✅ 刚修复 | 90% |
| 3. 计划编辑 | ✅ 完整 | ⚠️ API 缺失 | 60% |
| 4. Slide 并发生成 | ✅ 完整 | ❌ 断开连接 | 30% |
| 5. 单独编辑 | ✅ 完整 | ❌ 完全 Mock | 10% |
| 6. 导出 | ✅ 完整 | ⚠️ 待验证 | 70% |

### 需要修复的关键问题

1. **GenerationPage.tsx**: 移除 Mock 数据，正确从后端获取进度
2. **SlideEditorPage.tsx**: 实现 `loadData()` 加载真实幻灯片
3. **PlanEditorPage.tsx**: `generatePlan` 应该使用 `runAgent` API
4. **api/slides.py**: 验证 `start_generation` 能正确启动并发生成
5. **manifest.py**: 验证 `load_from_plan()` 兼容 Architect 输出格式

### 根本原因

重构版的前端页面（GenerationPage, SlideEditorPage）看起来是**设计稿/原型**，而不是完整的功能实现。代码中有大量 Mock 数据和 TODO 注释，说明这些页面没有真正连接到后端。

---

## 建议修复顺序

1. **第一阶段**: 验证 Architect 生成流程完整性
   - 运行 `runAgent` API
   - 检查生成的 `presentation_plan.json` 格式

2. **第二阶段**: 修复 PlanEditorPage
   - 移除 `generatePlan` API，使用 `runAgent`
   - 或在后端添加 `generatePlan` 端点

3. **第三阶段**: 修复 Slide 生成流程
   - 验证 `SlideGenerator.generate_all()` 工作正常
   - 修复 GenerationPage 使用真实数据

4. **第四阶段**: 修复 Slide 编辑
   - 在 SlideEditorPage 添加加载真实数据
   - 验证 AI 修改功能

5. **第五阶段**: 测试导出功能