import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { DetailedSlide, SlideContentItem, AIServiceStatus, Slide, SlideGenerationStatus } from '../types'
import { getTask, getSlide, updateSlide, modifySlideWithAI, getPlan, getGenerationProgress, getSlideHtmlUrl, AIMessage } from '../services/api'
import SlideThumbnail from '../components/SlideThumbnail'

// AI conversation context per slide
interface SlideAIContext {
  messages: AIMessage[]
}

// Extended slide with generation info
interface SlideWithGeneration extends DetailedSlide {
  generationStatus: 'queued' | 'running' | 'done' | 'failed'
  htmlContent?: string
  streamingContent?: string
}

// Helper to convert API Slide to DetailedSlide
function convertToDetailedSlide(slide: Slide, index: number): DetailedSlide {
  // Parse content - could be string or array
  let contentItems: SlideContentItem[] = []
  if (typeof slide.content === 'string') {
    // Split by newlines or bullets
    const lines = slide.content.split(/\n|•|·/).filter(l => l.trim())
    contentItems = lines.map((line, i) => ({
      id: `c${index}_${i}`,
      label: `要点 ${i + 1}`,
      value: line.trim()
    }))
  } else if (Array.isArray(slide.content)) {
    contentItems = (slide.content as string[]).map((item, i) => ({
      id: `c${index}_${i}`,
      label: `要点 ${i + 1}`,
      value: typeof item === 'string' ? item : String(item)
    }))
  }
  
  return {
    id: slide.id || `slide_${index + 1}`,
    title: slide.title || `幻灯片 ${index + 1}`,
    subtitle: slide.notes || '',
    layout: 'standard',
    content: contentItems.length > 0 ? contentItems : [
      { id: `c${index}_0`, label: '要点 1', value: '在此输入内容' }
    ]
  }
}

export default function SlideEditorPage() {
  const { taskId, slideIndex } = useParams<{ taskId: string; slideIndex?: string }>()
  const navigate = useNavigate()
  
  const [slides, setSlides] = useState<SlideWithGeneration[]>([])
  const [currentSlideId, setCurrentSlideId] = useState<string>('')
  const [aiPrompt, setAiPrompt] = useState('')
  const [aiStatus, setAiStatus] = useState<AIServiceStatus>(AIServiceStatus.IDLE)
  const [isInitializing, setIsInitializing] = useState(true)
  const [taskName, setTaskName] = useState('')
  const [currentStreamingContent, setCurrentStreamingContent] = useState<string>('')
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  
  // Per-slide AI context management
  const [aiContextMap, setAiContextMap] = useState<Map<string, SlideAIContext>>(new Map())
  const [aiMessages, setAiMessages] = useState<AIMessage[]>([])

  const currentSlide = slides.find(s => s.id === currentSlideId) || slides[0]
  const currentIdx = slides.findIndex(s => s.id === currentSlideId)
  const isCurrentSlideGenerating = currentSlide?.generationStatus === 'running'
  const [loadedHtmlContent, setLoadedHtmlContent] = useState<string>('')
  const [isLoadingHtml, setIsLoadingHtml] = useState(false)

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

  // Poll for generation progress
  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current)
    }
    
    pollIntervalRef.current = setInterval(async () => {
      if (!taskId) return
      try {
        const progress = await getGenerationProgress(taskId)
        if (progress?.slides) {
          setSlides(prev => prev.map(slide => {
            const progressSlide = progress.slides.find(p => p.id === slide.id)
            if (progressSlide) {
              return {
                ...slide,
                generationStatus: progressSlide.status,
                // TODO: Get actual HTML content from API when done
              }
            }
            return slide
          }))
          
          // Check if all done
          const allDone = progress.slides.every(s => s.status === 'done' || s.status === 'failed')
          if (allDone) {
            if (pollIntervalRef.current) {
              clearInterval(pollIntervalRef.current)
              pollIntervalRef.current = null
            }
          }
        }
      } catch (error) {
        console.error('Failed to fetch progress:', error)
      }
    }, 2000)
  }, [taskId])

  // Set current slide from URL param
  useEffect(() => {
    if (slideIndex && slides.length > 0) {
      const idx = parseInt(slideIndex, 10)
      if (idx >= 0 && idx < slides.length) {
        setCurrentSlideId(slides[idx].id)
      }
    } else if (slides.length > 0 && !currentSlideId) {
      setCurrentSlideId(slides[0].id)
    }
  }, [slideIndex, slides])

  // Load AI context when current slide changes
  useEffect(() => {
    if (currentSlideId) {
      const context = aiContextMap.get(currentSlideId)
      setAiMessages(context?.messages || [])
    }
  }, [currentSlideId, aiContextMap])

  // Load HTML content when current slide changes and is done
  useEffect(() => {
    const loadHtml = async () => {
      if (!taskId || !currentSlide || currentSlide.generationStatus !== 'done') {
        setLoadedHtmlContent('')
        return
      }
      
      setIsLoadingHtml(true)
      try {
        const url = getSlideHtmlUrl(taskId, currentIdx)
        const response = await fetch(url)
        if (response.ok) {
          const html = await response.text()
          setLoadedHtmlContent(html)
        } else {
          console.error('Failed to load HTML:', response.status)
          setLoadedHtmlContent('')
        }
      } catch (error) {
        console.error('Error loading HTML:', error)
        setLoadedHtmlContent('')
      } finally {
        setIsLoadingHtml(false)
      }
    }
    
    loadHtml()
  }, [taskId, currentSlide?.generationStatus, currentIdx])

  const loadData = async () => {
    setIsInitializing(true)
    try {
      const task = await getTask(taskId!)
      setTaskName(task.name)
      
      // Load presentation plan to get slides
      const plan = await getPlan(taskId!)
      
      // Also try to get generation progress
      const progress = await getGenerationProgress(taskId!).catch(() => null)
      
      if (plan?.slides && plan.slides.length > 0) {
        const detailedSlides: SlideWithGeneration[] = plan.slides.map((s, i) => {
          const base = convertToDetailedSlide(s, i)
          const progressSlide = progress?.slides?.find(p => p.id === base.id)
          return {
            ...base,
            generationStatus: progressSlide?.status || 'queued',
            htmlContent: undefined, // TODO: Load from API
            streamingContent: undefined
          }
        })
        setSlides(detailedSlides)
        if (!currentSlideId && detailedSlides.length > 0) {
          setCurrentSlideId(detailedSlides[0].id)
        }
        
        // Start polling if any slide is still generating
        const hasRunning = detailedSlides.some(s => s.generationStatus === 'running')
        if (hasRunning) {
          startPolling()
        }
      } else {
        // No slides yet, show empty state
        setSlides([])
      }
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setIsInitializing(false)
    }
  }

  const handleUpdateSlide = (updated: SlideWithGeneration) => {
    setSlides(prev => prev.map(s => s.id === updated.id ? { ...s, ...updated } : s))
  }

  const handleAddSlide = () => {
    const newSlide: SlideWithGeneration = {
      id: `slide-${Date.now()}`,
      title: '新幻灯片',
      subtitle: '添加描述',
      layout: 'standard',
      content: [{ id: `c-${Date.now()}`, label: '要点 1', value: '在此输入详情' }],
      generationStatus: 'queued'
    }
    setSlides(prev => [...prev, newSlide])
    setCurrentSlideId(newSlide.id)
  }

  const handleApplyAI = async () => {
    if (!aiPrompt.trim() || !currentSlideId) return
    setAiStatus(AIServiceStatus.LOADING)
    
    // Add user message to context
    const userMessage: AIMessage = { role: 'user', content: aiPrompt }
    const updatedMessages = [...aiMessages, userMessage]
    setAiMessages(updatedMessages)
    
    try {
      if (taskId) {
        // Call AI modify with conversation context
        const response = await modifySlideWithAI(taskId, currentIdx, aiPrompt, aiMessages)
        
        // Add AI response to context
        const assistantMessage: AIMessage = { role: 'assistant', content: response.message }
        const finalMessages = [...updatedMessages, assistantMessage]
        setAiMessages(finalMessages)
        
        // Save context to map for this slide
        setAiContextMap(prev => {
          const newMap = new Map(prev)
          newMap.set(currentSlideId, { messages: finalMessages })
          return newMap
        })
        
        // Reload HTML if slide was updated
        if (response.slide_updated) {
          // Trigger HTML reload by updating the loaded content
          const url = getSlideHtmlUrl(taskId, currentIdx)
          try {
            const htmlResponse = await fetch(url)
            if (htmlResponse.ok) {
              const html = await htmlResponse.text()
              setLoadedHtmlContent(html)
            }
          } catch (e) {
            console.error('Failed to reload HTML:', e)
          }
        }
        
        setAiStatus(response.success ? AIServiceStatus.IDLE : AIServiceStatus.ERROR)
      }
      setAiPrompt('')
    } catch (err) {
      console.error(err)
      // Add error message to context
      const errorMessage: AIMessage = { role: 'assistant', content: '抱歉，处理时出错了。请重试。' }
      const errorMessages = [...updatedMessages, errorMessage]
      setAiMessages(errorMessages)
      setAiContextMap(prev => {
        const newMap = new Map(prev)
        newMap.set(currentSlideId, { messages: errorMessages })
        return newMap
      })
      setAiStatus(AIServiceStatus.ERROR)
    }
  }

  const handleGenerateFull = async () => {
    const topic = window.prompt("请输入演示文稿的主题：")
    if (!topic) return
    setIsInitializing(true)
    try {
      // Generate presentation logic here
      await new Promise(resolve => setTimeout(resolve, 2000))
    } catch (err) {
      console.error(err)
    } finally {
      setIsInitializing(false)
    }
  }

  // Show loading state
  if (isInitializing) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#f8f9fa]">
        <div className="text-center">
          <span className="text-4xl animate-spin inline-block mb-4">⚙️</span>
          <p className="text-gray-500">加载幻灯片数据中...</p>
        </div>
      </div>
    )
  }

  // Show empty state if no slides
  if (slides.length === 0) {
    return (
      <div className="flex h-screen items-center justify-center bg-[#f8f9fa]">
        <div className="text-center max-w-md">
          <span className="text-6xl mb-4 block">📄</span>
          <h2 className="text-xl font-bold mb-2">暂无幻灯片</h2>
          <p className="text-gray-500 mb-4">请先在计划编辑页面添加幻灯片内容，或返回生成页面生成幻灯片。</p>
          <button
            onClick={() => navigate(`/task/${taskId}/plan`)}
            className="px-6 py-2 bg-black text-white rounded-lg hover:bg-gray-800 transition-colors"
          >
            前往计划编辑
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-[#f8f9fa] text-[#1a1a1a]">
      {/* Slide Navigation Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 flex flex-col h-full overflow-hidden">
        {/* Back to Grid View Button */}
        <div className="p-4 border-b border-gray-100">
          <button
            onClick={() => navigate(`/task/${taskId}/generate`)}
            className="w-full flex items-center gap-2 px-3 py-2 text-gray-600 hover:text-black hover:bg-gray-50 rounded-lg transition-all"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            <span className="text-sm font-medium">返回网格总览</span>
          </button>
        </div>
        
        <div className="p-4 border-b border-gray-100 flex items-center justify-between">
          <h2 className="font-bold text-sm uppercase tracking-widest text-gray-400">幻灯片列表</h2>
          <button
            onClick={handleAddSlide}
            className="p-1 hover:bg-gray-100 rounded-full transition-colors"
            title="添加幻灯片"
          >
            ➕
          </button>
        </div>
        
        <div className="flex-1 overflow-y-auto p-4 bg-gray-50/50">
          {slides.map((slide, index) => (
            <SlideThumbnail
              key={slide.id}
              slide={slide}
              index={index}
              isActive={slide.id === currentSlideId}
              onClick={() => setCurrentSlideId(slide.id)}
              status={slide.generationStatus}
              htmlContent={slide.htmlContent}
              htmlUrl={slide.generationStatus === 'done' && taskId ? getSlideHtmlUrl(taskId, index) : undefined}
              streamingContent={slide.streamingContent}
            />
          ))}
          <button 
            onClick={handleGenerateFull}
            className="w-full py-4 border-2 border-dashed border-gray-200 rounded-lg flex flex-col items-center justify-center text-gray-400 hover:border-black hover:text-black transition-all group"
          >
            <span className="mb-1 group-hover:scale-110 transition-transform">✨</span>
            <span className="text-[10px] font-bold uppercase">AI 一键生成</span>
          </button>
        </div>
      </aside>

      {/* Main Workspace */}
      <main className="flex-1 flex flex-col relative bg-[#fcfcfc]">
        {/* Header */}
        <header className="h-14 bg-white border-b border-gray-100 px-6 flex items-center z-10">
          <div className="flex items-center gap-4">
            <span className="text-lg font-bold tracking-tight">幻灯片编辑</span>
            <div className="h-4 w-[1px] bg-gray-200"></div>
            <span className="text-sm text-gray-400">第 {currentIdx + 1} 页，共 {slides.length} 页</span>
          </div>
        </header>

        {/* Preview Area - Read Only, no editing */}
        <div className="flex-1 overflow-hidden relative flex">
          {isInitializing ? (
            <div className="flex-1 flex flex-col items-center justify-center bg-white z-20">
              <span className="text-4xl animate-spin mb-4">⚙️</span>
              <p className="text-gray-500 font-medium animate-pulse">正在为您构建演示文稿...</p>
            </div>
          ) : currentSlide?.generationStatus === 'done' && loadedHtmlContent ? (
            // Show rendered HTML preview when done - use srcDoc for proper rendering
            <div className="flex-1 p-8 overflow-auto">
              <div className="max-w-4xl mx-auto">
                <div className="bg-white rounded-3xl shadow-xl border border-gray-100 overflow-hidden">
                  <div className="aspect-[16/9] relative overflow-hidden">
                    <iframe
                      srcDoc={loadedHtmlContent}
                      className="absolute top-0 left-0 border-0"
                      sandbox="allow-same-origin allow-scripts"
                      title={`Slide ${currentIdx + 1}`}
                      style={{
                        width: '1920px',
                        height: '1080px',
                        transform: 'scale(0.45)',
                        transformOrigin: 'top left'
                      }}
                    />
                  </div>
                </div>
              </div>
            </div>
          ) : currentSlide?.generationStatus === 'done' && isLoadingHtml ? (
            // Loading HTML
            <div className="flex-1 p-8 overflow-auto">
              <div className="max-w-4xl mx-auto">
                <div className="bg-white rounded-3xl shadow-xl border border-gray-100 overflow-hidden">
                  <div className="aspect-[16/9] flex items-center justify-center">
                    <span className="animate-spin text-2xl">⚙️</span>
                    <span className="ml-2 text-gray-500">加载幻灯片...</span>
                  </div>
                </div>
              </div>
            </div>
          ) : currentSlide?.generationStatus === 'running' ? (
            // Show streaming content while generating
            <div className="flex-1 p-8 overflow-auto">
              <div className="max-w-4xl mx-auto">
                <div className="bg-white rounded-3xl shadow-xl border border-gray-100 overflow-hidden">
                  <div className="p-4 border-b border-gray-100 flex items-center gap-3 bg-yellow-50">
                    <span className="animate-spin text-xl">⚙️</span>
                    <span className="text-sm font-medium text-yellow-700">正在生成幻灯片...</span>
                  </div>
                  <div className="aspect-[16/9] bg-gradient-to-br from-gray-50 to-white p-8 flex flex-col overflow-auto">
                    <h2 className="text-xl font-bold text-gray-800 mb-4">{currentSlide?.title}</h2>
                    {currentSlide?.streamingContent ? (
                      <div className="flex-1 overflow-auto">
                        <pre className="text-sm text-gray-600 whitespace-pre-wrap font-mono bg-gray-50 p-4 rounded-lg leading-relaxed">
                          {currentSlide.streamingContent}
                        </pre>
                      </div>
                    ) : (
                      <div className="flex-1 flex items-center justify-center">
                        <div className="text-center">
                          <div className="flex justify-center gap-1.5 mb-3">
                            <span className="w-2.5 h-2.5 bg-yellow-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></span>
                            <span className="w-2.5 h-2.5 bg-yellow-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></span>
                            <span className="w-2.5 h-2.5 bg-yellow-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></span>
                          </div>
                          <p className="text-sm text-gray-500">AI 正在生成 HTML 内容...</p>
                          <p className="text-xs text-gray-400 mt-1">请稍候，内容将实时显示</p>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ) : currentSlide?.generationStatus === 'failed' ? (
            // Show failed state
            <div className="flex-1 p-8 overflow-auto">
              <div className="max-w-4xl mx-auto">
                <div className="bg-white rounded-3xl shadow-xl border border-red-200 overflow-hidden">
                  <div className="p-4 border-b border-red-100 flex items-center gap-3 bg-red-50">
                    <span className="text-xl">❌</span>
                    <span className="text-sm font-medium text-red-700">生成失败</span>
                  </div>
                  <div className="aspect-[16/9] bg-gradient-to-br from-red-50 to-white p-8 flex flex-col items-center justify-center">
                    <span className="text-4xl mb-4">😔</span>
                    <h2 className="text-lg font-bold text-gray-800 mb-2">幻灯片生成失败</h2>
                    <p className="text-sm text-gray-500 mb-4">请尝试重新生成此幻灯片</p>
                    <button className="px-4 py-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors text-sm">
                      🔄 重新生成
                    </button>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            // Show queued/waiting state
            <div className="flex-1 p-8 overflow-auto">
              <div className="max-w-4xl mx-auto">
                <div className="bg-white rounded-3xl shadow-xl border border-gray-200 overflow-hidden">
                  <div className="p-4 border-b border-gray-100 flex items-center gap-3 bg-gray-50">
                    <span className="text-xl">⏳</span>
                    <span className="text-sm font-medium text-gray-600">等待生成</span>
                  </div>
                  <div className="aspect-[16/9] bg-gradient-to-br from-gray-50 to-white p-8 flex flex-col items-center justify-center">
                    <span className="text-4xl mb-4 opacity-50">📄</span>
                    <h2 className="text-lg font-bold text-gray-800 mb-2">{currentSlide?.title || '幻灯片'}</h2>
                    <p className="text-sm text-gray-500 mb-4">此幻灯片尚未开始生成</p>
                    <p className="text-xs text-gray-400">请返回网格总览，点击"启动待生成"开始生成</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* AI Panel */}
          <aside className="w-80 bg-white border-l border-gray-200 flex flex-col shadow-2xl z-30">
            <div className="p-6 border-b border-gray-100 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center">
                  ✨
                </div>
                <div>
                  <h3 className="font-bold text-sm tracking-wide">AI 设计助手</h3>
                  <span className="text-[10px] text-gray-400">第 {currentIdx + 1} 页</span>
                </div>
              </div>
              {aiMessages.length > 0 && (
                <button
                  onClick={() => {
                    setAiMessages([])
                    if (currentSlideId) {
                      setAiContextMap(prev => {
                        const newMap = new Map(prev)
                        newMap.delete(currentSlideId)
                        return newMap
                      })
                    }
                  }}
                  className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
                  title="清空对话"
                >
                  🗑️
                </button>
              )}
            </div>
            
            <div className="flex-1 p-6 overflow-y-auto space-y-4">
              {/* Welcome message - show only if no messages */}
              {aiMessages.length === 0 && (
                <div className="p-4 bg-gray-50 rounded-lg border border-gray-100 text-xs leading-relaxed text-gray-600">
                  您好！我可以帮您重新设计此幻灯片。尝试输入 <b>"使用网格布局"</b> 或 <b>"添加 3 个关键指标"</b>。
                </div>
              )}
              
              {/* Conversation history */}
              {aiMessages.map((msg, idx) => (
                <div
                  key={idx}
                  className={`p-3 rounded-lg text-xs leading-relaxed ${
                    msg.role === 'user'
                      ? 'bg-blue-50 text-blue-800 border border-blue-100 ml-4'
                      : 'bg-gray-50 text-gray-700 border border-gray-100 mr-4'
                  }`}
                >
                  <div className="font-bold text-[10px] uppercase tracking-wider mb-1 opacity-60">
                    {msg.role === 'user' ? '您' : 'AI 助手'}
                  </div>
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                </div>
              ))}
              
              {aiStatus === AIServiceStatus.LOADING && (
                <div className="flex items-center gap-2 p-3 bg-black/5 rounded-lg border border-black/10 animate-pulse">
                  <span className="animate-spin">⏳</span>
                  <span className="text-[10px] font-bold uppercase tracking-wider">正在处理更新...</span>
                </div>
              )}
            </div>

            <div className="p-6 pt-0">
              <div className="relative">
                <textarea
                  className="w-full bg-white border-2 border-gray-100 rounded-xl p-4 pr-12 text-sm focus:border-black outline-none transition-all min-h-[120px] shadow-sm resize-none"
                  placeholder="描述您想做的更改..."
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      handleApplyAI()
                    }
                  }}
                />
                <button 
                  onClick={handleApplyAI}
                  disabled={!aiPrompt.trim() || aiStatus === AIServiceStatus.LOADING}
                  className={`absolute right-3 bottom-3 p-2 rounded-lg transition-all ${
                    aiPrompt.trim() 
                      ? 'bg-black text-white hover:bg-gray-800' 
                      : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                  }`}
                >
                  ➤
                </button>
              </div>
              <p className="mt-3 text-[10px] text-gray-400 text-center uppercase tracking-widest font-bold">
                按回车键应用
              </p>
            </div>
          </aside>
        </div>

        {/* Footer Navigation */}
        <footer className="h-16 bg-white border-t border-gray-100 px-6 flex items-center justify-center z-10">
          <div className="flex gap-3">
            <button
              disabled={currentIdx === 0}
              onClick={() => setCurrentSlideId(slides[currentIdx - 1].id)}
              className="w-10 h-10 flex items-center justify-center rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-30 disabled:hover:bg-transparent transition-all"
            >
              ◀
            </button>
            <div className="flex items-center px-4 text-sm text-gray-500">
              {currentIdx + 1} / {slides.length}
            </div>
            <button
              disabled={currentIdx === slides.length - 1}
              onClick={() => setCurrentSlideId(slides[currentIdx + 1].id)}
              className="w-10 h-10 flex items-center justify-center rounded-lg border border-gray-200 hover:bg-gray-50 disabled:opacity-30 disabled:hover:bg-transparent transition-all"
            >
              ▶
            </button>
          </div>
        </footer>
      </main>
    </div>
  )
}