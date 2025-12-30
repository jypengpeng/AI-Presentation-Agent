import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Presentation, Slide, ViewMode } from '../types'
import { getTask, getPlan, savePlan, updateTaskPhase, startAgentGeneration, getAgentStatus } from '../services/api'
import SlideEditorCard from '../components/SlideEditorCard'

const INITIAL_PRESENTATION: Presentation = {
  title: "",
  slides: [],
  theme: {
    primaryColor: "#171717",
    accentColor: "#737373"
  }
}

export default function PlanEditorPage() {
  const { taskId } = useParams<{ taskId: string }>()
  const navigate = useNavigate()
  
  const [presentation, setPresentation] = useState<Presentation>(INITIAL_PRESENTATION)
  const [isGenerating, setIsGenerating] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('editor')
  const [prompt, setPrompt] = useState('')
  const [showPromptInput, setShowPromptInput] = useState(false)
  const [loading, setLoading] = useState(true)
  const [taskName, setTaskName] = useState('')

  useEffect(() => {
    if (taskId) {
      loadData()
    }
  }, [taskId])

  const loadData = async () => {
    try {
      const [task, plan] = await Promise.all([
        getTask(taskId!),
        getPlan(taskId!).catch(() => null)
      ])
      setTaskName(task.name)
      if (plan) {
        setPresentation(plan)
      }
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  const updateSlide = (updatedSlide: Slide) => {
    setPresentation(prev => ({
      ...prev,
      slides: prev.slides.map(s => s.id === updatedSlide.id ? updatedSlide : s)
    }))
  }

  const removeSlide = (id: string) => {
    if (presentation.slides.length <= 1) {
      alert("演示文稿至少需要包含一页内容。")
      return
    }
    setPresentation(prev => ({
      ...prev,
      slides: prev.slides.filter(s => s.id !== id)
    }))
  }

  const addSlide = () => {
    const newSlide: Slide = {
      id: `slide_${Date.now()}`,
      title: "",
      content: "",
      type: "content"
    }
    setPresentation(prev => ({
      ...prev,
      slides: [...prev.slides, newSlide]
    }))
    setTimeout(() => {
      window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
    }, 100)
  }

  const moveSlide = (index: number, direction: 'up' | 'down') => {
    const newSlides = [...presentation.slides]
    const targetIndex = direction === 'up' ? index - 1 : index + 1
    if (targetIndex >= 0 && targetIndex < newSlides.length) {
      [newSlides[index], newSlides[targetIndex]] = [newSlides[targetIndex], newSlides[index]]
      setPresentation({ ...presentation, slides: newSlides })
    }
  }

  const handleGenerate = async () => {
    if (!prompt || !taskId) return
    setIsGenerating(true)
    try {
      // Start Agent generation with architect phase
      await startAgentGeneration(taskId, prompt, 'architect')
      
      // Poll for completion
      const pollInterval = setInterval(async () => {
        try {
          const status = await getAgentStatus(taskId)
          if (status.status === 'completed' || status.plan_ready) {
            clearInterval(pollInterval)
            // Reload plan from backend
            const plan = await getPlan(taskId)
            setPresentation(plan)
            setShowPromptInput(false)
            setPrompt('')
            setIsGenerating(false)
          } else if (status.status === 'error') {
            clearInterval(pollInterval)
            setIsGenerating(false)
            alert(`生成失败: ${status.error || '未知错误'}`)
          }
        } catch (err) {
          console.error('Status poll error:', err)
        }
      }, 2000)
      
      // Timeout after 5 minutes
      setTimeout(() => {
        pollInterval && clearInterval(pollInterval)
        if (isGenerating) {
          setIsGenerating(false)
          alert('生成超时，请重试')
        }
      }, 300000)
    } catch (error) {
      console.error("生成失败", error)
      alert("生成失败，请检查网络或 API 状态。")
      setIsGenerating(false)
    }
  }

  const handleSave = async () => {
    if (!taskId) return
    try {
      await savePlan(taskId, presentation)
      alert('保存成功！')
    } catch (error) {
      console.error('保存失败:', error)
      alert('保存失败')
    }
  }

  const handleNextPhase = async () => {
    if (!taskId) return
    try {
      await savePlan(taskId, presentation)
      await updateTaskPhase(taskId, 'designing')
      navigate(`/task/${taskId}/generate`)
    } catch (error) {
      console.error('转换阶段失败:', error)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#fafafa]">
        <div className="text-gray-400">加载中...</div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex flex-col bg-[#fafafa] text-neutral-700">
      {/* Header */}
      <header className="sticky top-0 z-40 bg-white border-b border-neutral-100 px-8 py-4 flex justify-between items-center">
        <div className="flex items-center gap-4">
          <div className="w-10 h-10 bg-neutral-900 rounded-xl flex items-center justify-center text-white">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path d="M4 4h4v4H4V4zm8 0h4v4h-4V4zM4 12h4v4H4v-4zm8 0h4v4h-4v-4z" />
            </svg>
          </div>
          <div>
            <h1 className="text-lg font-black text-neutral-900 tracking-tighter uppercase">AIPresentation</h1>
            <p className="text-[9px] text-neutral-400 font-bold uppercase tracking-[0.2em]">Framework & Logic</p>
          </div>
        </div>
        
        <div className="flex gap-3">
          <button 
            onClick={() => setShowPromptInput(prev => !prev)}
            className={`px-5 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 border ${
              showPromptInput 
                ? 'bg-neutral-900 text-white border-neutral-900' 
                : 'bg-white border-neutral-200 text-neutral-500 hover:border-neutral-400 hover:text-neutral-900'
            }`}
          >
            ✨ {showPromptInput ? "取消 AI 生成" : "AI 智能扩写"}
          </button>
          <button 
            onClick={handleSave}
            className="px-6 py-2 bg-neutral-100 border border-neutral-200 text-neutral-600 rounded-xl text-xs font-bold hover:bg-neutral-200 transition-all flex items-center gap-2"
          >
            保存大纲 ↑
          </button>
          <button 
            onClick={handleNextPhase}
            className="px-6 py-2 bg-neutral-900 text-white rounded-xl text-xs font-bold hover:bg-black transition-all"
          >
            开始生成 →
          </button>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-8 grid grid-cols-1 lg:grid-cols-12 gap-12">
        {/* Left - Editor */}
        <div className="lg:col-span-8 space-y-10">
          {/* AI Input Panel */}
          {showPromptInput && (
            <div className="bg-white border border-neutral-200 p-8 rounded-2xl shadow-sm animate-fade-in">
              <div className="flex items-center gap-2 mb-6">
                <div className="w-1.5 h-1.5 rounded-full bg-neutral-900"></div>
                <h2 className="text-[10px] font-bold text-neutral-400 uppercase tracking-widest">AI ARCHITECT</h2>
              </div>
              <h3 className="text-lg font-bold text-neutral-800 mb-2">幻灯片逻辑构建指令</h3>
              <p className="text-neutral-400 text-xs mb-6 leading-relaxed">提供核心主题，AI 将为您拆解每一页的标题与关键论点内容。</p>
              <div className="flex gap-3">
                <input 
                  type="text" 
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="请输入您的演示文稿核心主题..."
                  className="flex-1 bg-neutral-50 border border-neutral-100 rounded-xl px-5 py-4 text-xs focus:outline-none focus:border-neutral-400 focus:bg-white transition-all text-neutral-800"
                  onKeyDown={(e) => e.key === 'Enter' && handleGenerate()}
                />
                <button 
                  disabled={isGenerating || !prompt.trim()}
                  onClick={handleGenerate}
                  className="bg-neutral-900 text-white px-8 py-4 rounded-xl text-xs font-bold hover:bg-black disabled:opacity-50 transition-all flex items-center gap-3 shadow-sm"
                >
                  {isGenerating ? '⏳' : '✨'} 立即生成
                </button>
              </div>
            </div>
          )}

          {/* Title Section */}
          <section className="bg-white p-12 rounded-[2rem] border border-neutral-100 shadow-sm relative group">
            <div className="absolute top-0 left-0 w-full h-1 bg-neutral-900 scale-x-0 group-hover:scale-x-100 transition-transform origin-left duration-500"></div>
            <div className="flex flex-col gap-3">
              <label className="text-[10px] font-bold text-neutral-300 uppercase tracking-[0.4em] mb-1 ml-1">Overall Presentation Title</label>
              <input 
                type="text" 
                className="w-full text-4xl font-black border-none focus:ring-0 px-0 outline-none leading-tight text-neutral-900 placeholder:text-neutral-100 transition-all bg-transparent"
                value={presentation.title}
                onChange={(e) => setPresentation({...presentation, title: e.target.value})}
                placeholder="请输入文稿总标题..."
              />
            </div>
          </section>

          {/* View Mode Toggle */}
          <div className="flex flex-col sm:flex-row justify-between items-center bg-white border border-neutral-100 p-3 rounded-2xl sticky top-24 z-30 shadow-sm gap-4">
            <div className="flex items-center gap-1 bg-neutral-50 p-1 rounded-xl border border-neutral-100">
              <button 
                onClick={() => setViewMode('editor')}
                className={`px-6 py-2 rounded-lg text-[11px] font-bold transition-all ${
                  viewMode === 'editor' 
                    ? 'bg-white text-neutral-900 shadow-sm border border-neutral-100' 
                    : 'text-neutral-400 hover:text-neutral-600'
                }`}
              >
                结构化编辑
              </button>
              <button 
                onClick={() => setViewMode('json')}
                className={`px-6 py-2 rounded-lg text-[11px] font-bold transition-all ${
                  viewMode === 'json' 
                    ? 'bg-white text-neutral-900 shadow-sm border border-neutral-100' 
                    : 'text-neutral-400 hover:text-neutral-600'
                }`}
              >
                JSON 源码
              </button>
            </div>
            
            <button 
              onClick={addSlide}
              className="w-full sm:w-auto px-7 py-2.5 bg-neutral-900 text-white rounded-xl text-xs font-bold hover:bg-black transition-all flex items-center justify-center gap-2 shadow-sm"
            >
              + 添加新页面
            </button>
          </div>

          {/* Content */}
          {viewMode === 'editor' ? (
            <div className="space-y-6">
              {presentation.slides.map((slide, index) => (
                <SlideEditorCard 
                  key={slide.id}
                  slide={slide}
                  index={index}
                  onUpdate={updateSlide}
                  onRemove={() => removeSlide(slide.id)}
                  onMoveUp={index > 0 ? () => moveSlide(index, 'up') : undefined}
                  onMoveDown={index < presentation.slides.length - 1 ? () => moveSlide(index, 'down') : undefined}
                />
              ))}
              
              <button 
                onClick={addSlide}
                className="w-full py-12 border-2 border-dashed border-neutral-100 rounded-[2rem] text-neutral-300 hover:border-neutral-300 hover:text-neutral-500 hover:bg-white transition-all flex flex-col items-center justify-center gap-3 group"
              >
                <div className="w-10 h-10 rounded-full bg-neutral-50 flex items-center justify-center group-hover:scale-110 transition-transform">
                  +
                </div>
                <span className="text-[10px] font-bold tracking-[0.2em] uppercase">增加一个新页面</span>
              </button>
            </div>
          ) : (
            <div className="bg-white rounded-3xl p-3 border border-neutral-100 shadow-sm overflow-hidden">
              <textarea 
                className="w-full h-[600px] bg-neutral-50/30 rounded-2xl text-neutral-600 font-mono text-[10px] focus:ring-0 p-10 leading-relaxed resize-none border-none outline-none"
                spellCheck={false}
                value={JSON.stringify(presentation, null, 2)}
                onChange={(e) => {
                  try {
                    const parsed = JSON.parse(e.target.value)
                    setPresentation(parsed)
                  } catch {}
                }}
              />
            </div>
          )}
        </div>

        {/* Right Sidebar */}
        <div className="lg:col-span-4">
          <div className="sticky top-28 space-y-10">
            <div className="bg-white rounded-[2rem] border border-neutral-100 p-10 shadow-sm">
              <div className="flex justify-between items-center mb-10">
                <h3 className="text-[10px] font-bold text-neutral-400 uppercase tracking-widest flex items-center gap-2">
                  📋 文档结构大纲
                </h3>
                <span className="text-[9px] font-bold text-neutral-900 bg-neutral-50 px-2 py-1 rounded border border-neutral-100">
                  {presentation.slides.length} 页
                </span>
              </div>
              
              <div className="space-y-8 relative">
                <div className="absolute left-[3px] top-1 bottom-1 w-[1px] bg-neutral-50"></div>
                {presentation.slides.map((slide, i) => (
                  <div key={slide.id} className="flex gap-6 group cursor-pointer relative items-start">
                    <div className="flex flex-col items-center pt-1.5">
                      <div className={`w-1.5 h-1.5 rounded-full transition-all z-10 ${
                        i === 0 ? 'bg-neutral-900 ring-4 ring-neutral-50' : 'bg-neutral-200 group-hover:bg-neutral-900'
                      }`}></div>
                    </div>
                    <div className="flex-1">
                      <h4 className="text-[11px] font-bold text-neutral-800 line-clamp-1 group-hover:text-neutral-900 transition-colors mb-1 leading-none">
                        {slide.title || "（空标题页面）"}
                      </h4>
                      <p className="text-[9px] text-neutral-400 font-mono uppercase">SLIDE {i+1} • {slide.type}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="text-center opacity-30 py-8">
              <p className="text-[8px] font-bold text-neutral-900 uppercase tracking-[0.8em]">AIPresentation v2.5</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}