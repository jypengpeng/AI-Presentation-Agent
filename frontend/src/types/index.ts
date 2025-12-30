// Task types
export interface Task {
  task_id: string
  name: string
  phase: TaskPhase
  status: TaskStatus
  slides_count: number
  created_at: string
  updated_at: string
}

export type TaskPhase = 
  | 'collecting' 
  | 'editing_plan' 
  | 'designing' 
  | 'completed'

export type TaskStatus = 
  | 'active' 
  | 'completed' 
  | 'archived' 
  | 'failed'

// Slide types
export interface Slide {
  id: string
  title: string
  content: string
  type: 'title' | 'content' | 'section' | 'end'
  notes?: string
}

export interface Presentation {
  title: string
  slides: Slide[]
  theme?: {
    primaryColor: string
    accentColor: string
  }
}

// Generation types
export interface GenerationProgress {
  total: number
  completed: number
  pending: number
  generating: number
  failed: number
  slides: SlideGenerationStatus[]
}

export interface SlideGenerationStatus {
  id: string
  title: string
  section?: string
  status: 'queued' | 'running' | 'done' | 'failed'
  progress: number
}

// View modes
export type ViewMode = 'editor' | 'json' | 'grid' | 'list'

// AI Service
export enum AIServiceStatus {
  IDLE = 'idle',
  LOADING = 'loading',
  SUCCESS = 'success',
  ERROR = 'error'
}

// Slide content item
export interface SlideContentItem {
  id: string
  label: string
  value: string
}

export interface DetailedSlide {
  id: string
  title: string
  subtitle?: string
  layout: 'standard' | 'grid' | 'minimal'
  content: SlideContentItem[]
}

// Quick templates
export const QUICK_TEMPLATES: Record<string, string> = {
  '年度总结': '请为公司年度总结生成 PPT：经营指标、亮点、团队成就、问题复盘、来年规划。建议 12-18 页。',
  '产品发布会': '新品发布会：愿景定位、用户痛点、功能演示、技术亮点、路线图、价格与计划、Q&A。',
  '项目汇报': '项目阶段汇报：目标、里程碑、当前进度、风险/对策、资源需求、下一步计划。',
  '商业计划书': '商业计划书：市场分析、商业模式、产品方案、竞争壁垒、财务预测、团队与融资。'
}