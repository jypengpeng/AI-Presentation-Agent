import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { SlideGenerationStatus, ViewMode } from '../types'
import {
  getTask,
  getGenerationProgress,
  startGeneration,
  regenerateSlide,
  getExportUrl,
  getPlan,
  getSlideHtmlUrl
} from '../services/api'

export default function GenerationPage() {
  const { taskId } = useParams<{ taskId: string }>()
  const navigate = useNavigate()
  
  const [slides, setSlides] = useState<SlideGenerationStatus[]>([])
  const [query, setQuery] = useState('')
  const [view, setView] = useState<'grid' | 'list'>('grid')
  const [filters, setFilters] = useState({ queued: true, running: true, done: true })
  const [taskName, setTaskName] = useState('')
  const [loading, setLoading] = useState(true)
  const [isGenerating, setIsGenerating] = useState(false)
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [htmlPreviews, setHtmlPreviews] = useState<Record<string, string>>({})

  // Load initial data
  useEffect(() => {
    if (taskId) {
      loadData()
    }
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
      }
    }
  }, [taskId])

  // Load HTML preview for completed slides
  const loadHtmlPreview = useCallback(async (slideId: string, slideIndex: number) => {
    if (!taskId || htmlPreviews[slideId]) return
    try {
      const url = getSlideHtmlUrl(taskId, slideIndex)
      const response = await fetch(url)
      if (response.ok) {
        const html = await response.text()
        setHtmlPreviews(prev => ({ ...prev, [slideId]: html }))
      }
    } catch (error) {
      console.error('Error loading HTML preview:', error)
    }
  }, [taskId, htmlPreviews])

  // Load previews for done slides
  useEffect(() => {
    slides.forEach((slide, index) => {
      if (slide.status === 'done' && !htmlPreviews[slide.id]) {
        loadHtmlPreview(slide.id, index)
      }
    })
  }, [slides, loadHtmlPreview])

  // Poll for progress updates when generating
  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
    }
    
    pollIntervalRef.current = setInterval(async () => {
      if (!taskId) return
      try {
        const progress = await getGenerationProgress(taskId)
        if (progress?.slides) {
          setSlides(progress.slides)
        }
        
        // Check if all done
        const allDone = progress?.slides?.every(s => s.status === 'done' || s.status === 'failed')
        if (allDone && progress?.slides?.length > 0) {
          setIsGenerating(false)
          if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current)
            pollIntervalRef.current = null
          }
        }
      } catch (error) {
        console.error('Failed to fetch progress:', error)
      }
    }, 2000)
  }, [taskId])

  const loadData = async () => {
    try {
      const task = await getTask(taskId!)
      setTaskName(task.name)
      
      // Load both plan and progress to merge them
      const [plan, progress] = await Promise.all([
        getPlan(taskId!).catch(() => null),
        getGenerationProgress(taskId!).catch(() => null)
      ])
      
      // Create a map of progress by slide ID for quick lookup
      const progressMap = new Map<string, SlideGenerationStatus>()
      if (progress?.slides) {
        progress.slides.forEach(s => progressMap.set(s.id, s))
      }
      
      // Build slides list - use plan as base, merge with progress
      if (plan?.slides && plan.slides.length > 0) {
        const slidesWithProgress: SlideGenerationStatus[] = plan.slides.map((s, i) => {
          const slideId = s.id || `slide_${i + 1}`
          const progressSlide = progressMap.get(slideId)
          
          return {
            id: slideId,
            title: s.title || `幻灯片 ${i + 1}`,
            section: s.type || 'content',
            // Use progress status if available, otherwise default to queued
            status: progressSlide?.status || 'queued' as const,
            progress: progressSlide?.progress || 0
          }
        })
        setSlides(slidesWithProgress)
        
        // Check if still generating - start polling if any slide is running
        const hasRunning = slidesWithProgress.some(s => s.status === 'running')
        if (hasRunning) {
          setIsGenerating(true)
          startPolling()
        }
      } else if (progress?.slides && progress.slides.length > 0) {
        // Fallback: use progress data directly if no plan
        setSlides(progress.slides)
        const hasRunning = progress.slides.some(s => s.status === 'running')
        if (hasRunning) {
          setIsGenerating(true)
          startPolling()
        }
      }
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  const filtered = useMemo(() => {
    const allowed = new Set<string>([
      ...(filters.queued ? ['queued'] : []),
      ...(filters.running ? ['running'] : []),
      ...(filters.done ? ['done'] : []),
    ])
    return slides.filter(s => 
      allowed.has(s.status) && 
      (!query || s.title.toLowerCase().includes(query.toLowerCase()))
    )
  }, [slides, query, filters])

  const overall = useMemo(() => {
    const total = slides.length || 1
    const completed = slides.filter(s => s.status === 'done').length
    const percent = Math.round((completed / total) * 100)
    return { total, completed, percent }
  }, [slides])

  const handleRegenerate = (id: string) => {
    setSlides(prev => prev.map(s => 
      s.id === id ? { ...s, status: 'running', progress: Math.min(s.progress, 5) } : s
    ))
    if (taskId) {
      regenerateSlide(taskId, id).catch(console.error)
    }
  }

  const handleStartAllQueued = async () => {
    if (!taskId) return
    
    // Optimistically update UI
    setSlides(prev => prev.map(s =>
      s.status === 'queued' ? { ...s, status: 'running', progress: 1 } : s
    ))
    setIsGenerating(true)
    
    try {
      await startGeneration(taskId)
      // Start polling for updates
      startPolling()
    } catch (error) {
      console.error('Failed to start generation:', error)
      alert('启动生成失败，请重试')
      setIsGenerating(false)
      // Revert optimistic update
      setSlides(prev => prev.map(s =>
        s.status === 'running' && s.progress <= 1 ? { ...s, status: 'queued', progress: 0 } : s
      ))
    }
  }

  const handleDelete = (id: string) => {
    setSlides(prev => prev.filter(s => s.id !== id))
  }

  const handleAddSlide = () => {
    const nextId = String(Math.max(0, ...slides.map(s => Number(s.id))) + 1)
    setSlides(prev => [
      ...prev,
      { id: nextId, title: `新增页面 ${nextId}`, section: "新建", status: 'queued', progress: 0 },
    ])
  }

  const handleExport = (format: 'html' | 'pptx' | 'zip') => {
    if (taskId) {
      window.open(getExportUrl(taskId, format), '_blank')
    }
  }

  const pct = (n: number) => Math.max(0, Math.min(100, Math.round(n)))

  const statusBadge = (status: SlideGenerationStatus['status']) => {
    const map = {
      queued: { label: '待生成', bg: 'bg-gray-100', text: 'text-gray-600', icon: '⏳' },
      running: { label: '生成中', bg: 'bg-yellow-100', text: 'text-yellow-800', icon: '⚙️' },
      done: { label: '已完成', bg: 'bg-emerald-100', text: 'text-emerald-800', icon: '✓' },
      failed: { label: '失败', bg: 'bg-red-100', text: 'text-red-800', icon: '✕' }
    }
    const item = map[status] || map.queued
    return (
      <span className={`${item.bg} ${item.text} px-2.5 py-1 rounded-full text-xs font-medium flex items-center gap-1.5`}>
        <span className={status === 'running' ? 'animate-spin' : ''}>{item.icon}</span>
        {item.label}
      </span>
    )
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-gray-400">加载中...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen w-full bg-gray-50 text-gray-900">
      {/* Top Bar */}
      <header className="sticky top-0 z-20 border-b bg-white/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-6 py-4">
          <span className="text-xl">📄</span>
          <h1 className="text-xl font-semibold tracking-tight">AI Presentation Agent · 幻灯片生成监控</h1>
          <div className="ml-auto flex items-center gap-2">
            {/* Search */}
            <div className="hidden md:flex items-center gap-2 rounded-xl border px-3 py-2 bg-white">
              <span className="text-gray-400">🔍</span>
              <input 
                value={query} 
                onChange={e => setQuery(e.target.value)} 
                placeholder="搜索页面标题…" 
                className="h-8 w-[220px] border-0 p-0 outline-none bg-transparent text-sm"
              />
            </div>

            {/* Filter Dropdown */}
            <div className="relative group">
              <button className="px-4 py-2 border rounded-lg hover:bg-gray-50 flex items-center gap-2 text-sm font-medium">
                🔽 筛选
              </button>
              <div className="absolute right-0 top-full mt-2 w-40 bg-white border rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
                <div className="p-2 text-xs font-semibold text-gray-500 border-b">任务状态</div>
                {([
                  { key: 'queued', label: '待生成' },
                  { key: 'running', label: '生成中' },
                  { key: 'done', label: '已完成' },
                ] as const).map(({ key, label }) => (
                  <label key={key} className="flex items-center gap-2 px-3 py-2 hover:bg-gray-50 cursor-pointer">
                    <input 
                      type="checkbox" 
                      checked={filters[key]}
                      onChange={(e) => setFilters(p => ({ ...p, [key]: e.target.checked }))}
                      className="rounded"
                    />
                    <span className="text-sm">{label}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* View Toggle */}
            <button 
              onClick={() => setView(v => v === 'grid' ? 'list' : 'grid')}
              className="px-4 py-2 border rounded-lg hover:bg-gray-50 flex items-center gap-2 text-sm font-medium"
            >
              📊 {view === 'grid' ? '网格' : '列表'}
            </button>
            
            <button 
              onClick={handleAddSlide}
              className="px-4 py-2 bg-gray-900 text-white rounded-lg hover:bg-black flex items-center gap-2 text-sm font-medium"
            >
              ▶ 新增任务
            </button>
          </div>
        </div>
      </header>

      {/* Summary Card */}
      <section className="mx-auto max-w-7xl px-6 pt-6">
        <div className="bg-white border border-dashed rounded-xl p-6">
          <div className="flex items-center justify-between mb-2">
            <h2 className="font-semibold">项目总进度</h2>
            <span className="text-sm text-gray-500">已完成 {overall.completed} / {overall.total} 个页面</span>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
              <div 
                className="h-full bg-gray-900 transition-all duration-500"
                style={{ width: `${overall.percent}%` }}
              />
            </div>
            <span className="w-14 text-right text-sm font-medium">{overall.percent}%</span>
            <div className="ml-auto flex gap-2">
              <button 
                onClick={handleStartAllQueued}
                className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg flex items-center gap-2 text-sm font-medium"
              >
                ▶ 启动待生成
              </button>
              <div className="relative group">
                <button
                  className="px-4 py-2 border rounded-lg hover:bg-gray-50 flex items-center gap-2 text-sm font-medium"
                >
                  ⬇ 导出
                </button>
                <div className="absolute right-0 top-full mt-2 w-56 bg-white border rounded-lg shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-50">
                  <div className="p-2 text-xs font-semibold text-gray-500 border-b">导出选项</div>
                  <button
                    onClick={() => handleExport('zip')}
                    className="w-full px-3 py-2 hover:bg-gray-50 text-left flex items-center gap-2 text-sm"
                  >
                    📦 完整包 (ZIP)
                    <span className="text-xs text-gray-400 ml-auto">推荐</span>
                  </button>
                  <button
                    onClick={() => handleExport('html')}
                    className="w-full px-3 py-2 hover:bg-gray-50 text-left flex items-center gap-2 text-sm"
                  >
                    🌐 网页版 (HTML)
                  </button>
                  <button
                    onClick={() => handleExport('pptx')}
                    className="w-full px-3 py-2 hover:bg-gray-50 text-left flex items-center gap-2 text-sm"
                  >
                    📊 PowerPoint (PPTX)
                  </button>
                  <div className="border-t p-2 text-xs text-gray-500">
                    完整包包含: HTML、PPTX、演讲稿
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Content Tabs */}
      <main className="mx-auto max-w-7xl px-6 py-6">
        <div className="flex gap-1 mb-4 bg-gray-100 p-1 rounded-lg w-fit">
          {['全部', '待生成', '生成中', '已完成'].map((tab, i) => (
            <button
              key={tab}
              className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                i === 0 ? 'bg-white shadow-sm' : 'hover:bg-gray-50'
              }`}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Grid View */}
        {view === 'grid' ? (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            <AnimatePresence>
              {filtered.map(item => (
                <motion.div 
                  key={item.id}
                  layout
                  initial={{ opacity: 0, scale: 0.98 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0 }}
                >
                  <div className="bg-white border rounded-2xl p-4 hover:shadow-lg transition-shadow group">
                    {/* Header */}
                    <div className="flex items-start justify-between gap-2 mb-3">
                      <div>
                        <h3 className="font-semibold text-sm leading-tight line-clamp-2">{item.title}</h3>
                        <p className="text-xs text-gray-500 mt-1">{item.section || "章节"}</p>
                      </div>
                      <div className="relative">
                        <button className="p-1.5 hover:bg-gray-100 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity">
                          ⋯
                        </button>
                      </div>
                    </div>

                    {/* Status & ID */}
                    <div className="flex items-center justify-between mb-3">
                      {statusBadge(item.status)}
                      <span className="text-xs text-gray-400">#{item.id}</span>
                    </div>

                    {/* Preview */}
                    <div className="relative mb-3 aspect-[16/9] w-full overflow-hidden rounded-xl border bg-white flex items-center justify-center">
                      {item.status === 'done' && htmlPreviews[item.id] ? (
                        <div className="w-full h-full relative overflow-hidden">
                          <iframe
                            srcDoc={htmlPreviews[item.id]}
                            className="absolute top-0 left-0 pointer-events-none border-0"
                            sandbox="allow-same-origin allow-scripts"
                            title={`Preview ${item.id}`}
                            style={{
                              width: '1920px',
                              height: '1080px',
                              transform: 'scale(0.15)',
                              transformOrigin: 'top left'
                            }}
                          />
                        </div>
                      ) : item.status === 'done' ? (
                        <span className="text-sm text-gray-400">加载预览...</span>
                      ) : item.status === 'running' ? (
                        <span className="animate-spin text-2xl">⚙️</span>
                      ) : (
                        <span className="text-sm text-gray-400">等待生成</span>
                      )}
                    </div>

                    {/* Progress */}
                    <div className="flex items-center gap-3 mb-3">
                      <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                        <div 
                          className={`h-full transition-all duration-300 ${
                            item.status === 'done' ? 'bg-emerald-500' : 
                            item.status === 'running' ? 'bg-yellow-500' : 'bg-gray-300'
                          }`}
                          style={{ width: `${pct(item.progress)}%` }}
                        />
                      </div>
                      <span className="w-10 text-right text-xs">{pct(item.progress)}%</span>
                    </div>

                    {/* Actions */}
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          // Extract numeric index from slide ID (e.g., "slide_1" -> 0)
                          const idx = slides.findIndex(s => s.id === item.id)
                          navigate(`/task/${taskId}/slides/${idx >= 0 ? idx : 0}`)
                        }}
                        className="flex-1 px-3 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-xs font-medium flex items-center justify-center gap-1"
                      >
                        🔍 查看 / 编辑
                      </button>
                      <button 
                        onClick={() => handleRegenerate(item.id)}
                        className="px-3 py-2 border rounded-lg hover:bg-gray-50 text-xs font-medium flex items-center gap-1"
                      >
                        🔄 重新生成
                      </button>
                    </div>
                  </div>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        ) : (
          /* List View */
          <div className="divide-y rounded-xl border bg-white">
            {filtered.map(item => (
              <div key={item.id} className="grid grid-cols-12 items-center gap-3 px-4 py-3">
                <div className="col-span-6 flex items-center gap-3">
                  <div className="h-12 w-20 rounded-md border bg-gray-50 flex items-center justify-center text-xs text-gray-400">
                    预览
                  </div>
                  <div>
                    <div className="font-medium leading-tight">{item.title}</div>
                    <div className="text-xs text-gray-500">{item.section || "章节"}</div>
                  </div>
                </div>
                <div className="col-span-2 flex items-center">
                  {statusBadge(item.status)}
                </div>
                <div className="col-span-2 flex items-center gap-3">
                  <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-gray-900"
                      style={{ width: `${pct(item.progress)}%` }}
                    />
                  </div>
                  <span className="w-10 text-right text-xs">{pct(item.progress)}%</span>
                </div>
                <div className="col-span-2 flex justify-end gap-2">
                                  <button
                                    onClick={() => {
                                      const idx = slides.findIndex(s => s.id === item.id)
                                      navigate(`/task/${taskId}/slides/${idx >= 0 ? idx : 0}`)
                                    }}
                                    className="px-3 py-1.5 bg-gray-100 hover:bg-gray-200 rounded text-xs font-medium"
                                  >
                                    查看
                                  </button>
                  <button 
                    onClick={() => handleRegenerate(item.id)}
                    className="px-3 py-1.5 border rounded hover:bg-gray-50 text-xs font-medium"
                  >
                    重生
                  </button>
                  <button 
                    onClick={() => handleDelete(item.id)}
                    className="px-3 py-1.5 text-red-500 hover:bg-red-50 rounded text-xs font-medium"
                  >
                    删除
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      <footer className="mx-auto max-w-7xl px-6 pb-14 text-center text-xs text-gray-500">
        {isGenerating ? '正在生成中，每 2 秒自动刷新进度...' : '点击「启动待生成」开始生成幻灯片'}
      </footer>
    </div>
  )
}