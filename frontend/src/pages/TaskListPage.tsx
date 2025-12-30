import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Task, QUICK_TEMPLATES } from '../types'
import {
  getTasks,
  createTask,
  deleteTask,
  submitIdea,
  uploadFiles,
  uploadDirectory,
  listUploadedFiles,
  startAgentGeneration,
  getAgentStatus,
  UploadResult,
  FileInfo,
  AgentStatus
} from '../services/api'
import { filterFiles, getIgnoreSummary } from '../utils/gitignore'

// WebSocket URL
const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'

// Helper to format file size
function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export default function TaskListPage() {
  const navigate = useNavigate()
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null)
  const [taskName, setTaskName] = useState('')
  const [htmlPath, setHtmlPath] = useState('')
  const [idea, setIdea] = useState('')
  const [showDrawer, setShowDrawer] = useState(false)
  const [isCreating, setIsCreating] = useState(false)
  
  // Upload related state
  const [showUploadDialog, setShowUploadDialog] = useState(false)
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [filteredFiles, setFilteredFiles] = useState<File[]>([])
  const [ignoredCount, setIgnoredCount] = useState(0)
  const [ignoreSummary, setIgnoreSummary] = useState('')
  const [isDirectoryUpload, setIsDirectoryUpload] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<string>('')
  const [uploadedFiles, setUploadedFiles] = useState<FileInfo[]>([])
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null)
  
  // Agent generation state
  const [isGenerating, setIsGenerating] = useState(false)
  const [generationStatus, setGenerationStatus] = useState<AgentStatus | null>(null)
  const [generationError, setGenerationError] = useState<string | null>(null)
  const [streamingContent, setStreamingContent] = useState<string>('')
  const [currentPhase, setCurrentPhase] = useState<string>('初始化')
  
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dirInputRef = useRef<HTMLInputElement>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const streamingContentRef = useRef<HTMLDivElement>(null)

  // Load tasks
  useEffect(() => {
    loadTasks()
  }, [])

  const loadTasks = async () => {
    try {
      const data = await getTasks()
      setTasks(data)
      if (data.length > 0 && !activeTaskId) {
        setActiveTaskId(data[0].task_id)
        setTaskName(data[0].name)
      }
    } catch (error) {
      console.error('Failed to load tasks:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleNewTask = async () => {
    // First create the task to get an ID
    const name = `任务 ${tasks.length + 1}`
    setIsCreating(true)
    try {
      const newTask = await createTask(name)
      setPendingTaskId(newTask.task_id)
      setTaskName(newTask.name)
      // Show upload dialog
      setShowUploadDialog(true)
      setSelectedFiles([])
      setUploadedFiles([])
      setUploadProgress('')
    } catch (error) {
      console.error('Failed to create task:', error)
    } finally {
      setIsCreating(false)
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    if (files && files.length > 0) {
      const fileArray: File[] = Array.from(files)
      setSelectedFiles(fileArray)
      setIsDirectoryUpload(false)
      
      // Apply gitignore filter
      const result = filterFiles(fileArray, (file: File) => file.name)
      setFilteredFiles(result.filtered)
      setIgnoredCount(result.ignoredCount)
      setIgnoreSummary(getIgnoreSummary(result.ignoredPaths))
    }
  }

  const handleDirectorySelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files
    console.log('[Upload Debug] handleDirectorySelect called')
    console.log('[Upload Debug] files from input:', files?.length)
    
    if (files && files.length > 0) {
      const fileArray: File[] = Array.from(files)
      console.log('[Upload Debug] Total files selected:', fileArray.length)
      
      // Log first few files for debugging
      fileArray.slice(0, 5).forEach((file, i) => {
        console.log(`[Upload Debug] File ${i}: name=${file.name}, webkitRelativePath=${(file as any).webkitRelativePath}`)
      })
      
      setSelectedFiles(fileArray)
      setIsDirectoryUpload(true)
      
      // Apply gitignore filter using relative paths
      const result = filterFiles(fileArray, (file: File) => {
        return (file as any).webkitRelativePath || file.name
      })
      
      console.log('[Upload Debug] After gitignore filter:')
      console.log('[Upload Debug] - Filtered (to upload):', result.filtered.length)
      console.log('[Upload Debug] - Ignored:', result.ignoredCount)
      console.log('[Upload Debug] - Ignored paths sample:', result.ignoredPaths.slice(0, 5))
      
      setFilteredFiles(result.filtered)
      setIgnoredCount(result.ignoredCount)
      setIgnoreSummary(getIgnoreSummary(result.ignoredPaths))
    }
  }

  const handleUpload = async () => {
    console.log('[Upload Debug] handleUpload called')
    console.log('[Upload Debug] pendingTaskId:', pendingTaskId)
    console.log('[Upload Debug] filteredFiles.length:', filteredFiles.length)
    
    if (!pendingTaskId || filteredFiles.length === 0) {
      console.log('[Upload Debug] Early return - no task or no files')
      return
    }
    
    setIsUploading(true)
    setUploadProgress('正在上传...')
    
    try {
      let result: UploadResult
      
      if (isDirectoryUpload) {
        // For directory upload, extract relative paths from webkitRelativePath
        const filesWithPaths = filteredFiles.map(file => {
          // webkitRelativePath contains the full relative path
          const relativePath = (file as any).webkitRelativePath || file.name
          return { file, path: relativePath }
        })
        
        console.log('[Upload Debug] Directory upload mode')
        console.log('[Upload Debug] Files to upload:', filesWithPaths.length)
        console.log('[Upload Debug] Sample paths:', filesWithPaths.slice(0, 5).map(f => f.path))
        
        // Upload with relative paths
        result = await uploadFiles(
          pendingTaskId,
          filesWithPaths.map(f => f.file),
          filesWithPaths.map(f => f.path)
        )
      } else {
        console.log('[Upload Debug] Simple file upload mode')
        // Simple file upload
        result = await uploadFiles(pendingTaskId, filteredFiles)
      }
      
      console.log('[Upload Debug] Upload result:', result)
      
      let progressMsg = `已上传 ${result.files_uploaded} 个文件 (${formatFileSize(result.total_size_bytes)})`
      if (ignoredCount > 0) {
        progressMsg += `，已过滤 ${ignoredCount} 个文件`
      }
      setUploadProgress(progressMsg)
      
      // Refresh file list
      const summary = await listUploadedFiles(pendingTaskId)
      setUploadedFiles(summary.files)
      
    } catch (error) {
      console.error('Upload failed:', error)
      setUploadProgress('上传失败')
    } finally {
      setIsUploading(false)
    }
  }

  const handleConfirmTask = async () => {
    if (!pendingTaskId) return
    
    // Load the tasks again to get the new one
    await loadTasks()
    
    // Set as active task
    setActiveTaskId(pendingTaskId)
    
    // Close dialog
    setShowUploadDialog(false)
    setPendingTaskId(null)
    setSelectedFiles([])
    setUploadedFiles([])
  }

  const handleCancelNewTask = async () => {
    if (pendingTaskId) {
      // Delete the task that was created
      try {
        await deleteTask(pendingTaskId)
      } catch (error) {
        console.error('Failed to delete pending task:', error)
      }
    }
    
    setShowUploadDialog(false)
    setPendingTaskId(null)
    setSelectedFiles([])
    setFilteredFiles([])
    setIgnoredCount(0)
    setIgnoreSummary('')
    setUploadedFiles([])
    setUploadProgress('')
  }

  const handleDeleteTask = async (taskId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await deleteTask(taskId)
      const newTasks = tasks.filter(t => t.task_id !== taskId)
      setTasks(newTasks)
      if (activeTaskId === taskId) {
        setActiveTaskId(newTasks[0]?.task_id || null)
        setTaskName(newTasks[0]?.name || '')
      }
    } catch (error) {
      console.error('Failed to delete task:', error)
    }
  }

  const handleSelectTask = (task: Task) => {
    setActiveTaskId(task.task_id)
    setTaskName(task.name)
  }

  const handleQuickTemplate = (template: string) => {
    setIdea(QUICK_TEMPLATES[template] || '')
  }

  // Scroll streaming content to bottom
  const scrollToBottom = useCallback(() => {
    if (streamingContentRef.current) {
      streamingContentRef.current.scrollTop = streamingContentRef.current.scrollHeight
    }
  }, [])

  // WebSocket streaming generation
  const handleGenerate = useCallback(async () => {
    if (!idea.trim() || !activeTaskId) return
    
    setIsGenerating(true)
    setGenerationError(null)
    setStreamingContent('')
    setCurrentPhase('初始化')
    setShowDrawer(true)
    
    // Close existing WebSocket if any
    if (wsRef.current) {
      wsRef.current.close()
    }
    
    try {
      // Connect to WebSocket for streaming
      const ws = new WebSocket(`${WS_BASE}/tasks/${activeTaskId}/agent/stream`)
      wsRef.current = ws
      
      ws.onopen = () => {
        console.log('WebSocket connected')
        // Send start message
        ws.send(JSON.stringify({
          type: 'start',
          message: idea
        }))
      }
      
      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          
          switch (data.type) {
            case 'connected':
              console.log('Agent connected for task:', data.task_id)
              break
              
            case 'phase':
              setCurrentPhase(data.phase === 'collecting' ? '信息收集' :
                             data.phase === 'architect' ? '架构规划' :
                             data.phase || '处理中')
              break
              
            case 'chunk':
              setStreamingContent(prev => prev + data.content)
              scrollToBottom()
              break
              
            case 'tool_call':
              setStreamingContent(prev => prev + `\n[调用工具: ${data.name}]\n`)
              scrollToBottom()
              break
              
            case 'tool_result':
              setStreamingContent(prev => prev + `[工具结果: ${data.status}]\n`)
              scrollToBottom()
              break
              
            case 'complete':
              setIsGenerating(false)
              if (data.plan_ready) {
                setCurrentPhase('✓ 框架提纲生成完成')
                setGenerationStatus({
                  status: 'completed',
                  phase: data.phase,
                  plan_ready: true,
                  plan_exists: true
                })
                // Don't auto-navigate, let user review the output first
                // User can click "前往编辑" button to proceed
              } else {
                setCurrentPhase('生成未完成')
                setGenerationStatus({
                  status: 'completed',
                  phase: data.phase,
                  plan_ready: false
                })
              }
              break
              
            case 'error':
              setIsGenerating(false)
              setGenerationError(data.message || '生成失败')
              break
              
            case 'aborted':
              setIsGenerating(false)
              setCurrentPhase('已取消')
              break
          }
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e)
        }
      }
      
      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        setGenerationError('WebSocket 连接错误，尝试使用轮询模式...')
        // Fallback to polling
        fallbackToPolling()
      }
      
      ws.onclose = () => {
        console.log('WebSocket closed')
        wsRef.current = null
      }
      
    } catch (error) {
      console.error('Failed to connect WebSocket:', error)
      // Fallback to polling mode
      fallbackToPolling()
    }
  }, [idea, activeTaskId, navigate, scrollToBottom])
  
  // Fallback to REST API polling
  const fallbackToPolling = useCallback(async () => {
    if (!activeTaskId) return
    
    try {
      await startAgentGeneration(activeTaskId, idea)
      
      const pollStatus = async () => {
        try {
          const status = await getAgentStatus(activeTaskId)
          setGenerationStatus(status)
          setCurrentPhase(status.phase || '处理中')
          
          if (status.status === 'completed') {
            setIsGenerating(false)
            if (status.plan_ready || status.plan_exists) {
              navigate(`/task/${activeTaskId}/plan`)
            }
          } else if (status.status === 'error') {
            setIsGenerating(false)
            setGenerationError(status.error || 'Generation failed')
          } else if (status.status === 'running') {
            setTimeout(pollStatus, 2000)
          }
        } catch (error) {
          console.error('Failed to get agent status:', error)
          setTimeout(pollStatus, 3000)
        }
      }
      
      setTimeout(pollStatus, 1000)
    } catch (error) {
      console.error('Failed to start generation:', error)
      setIsGenerating(false)
      setGenerationError(error instanceof Error ? error.message : 'Failed to start generation')
    }
  }, [activeTaskId, idea, navigate])

  // Cancel generation
  const handleCancelGeneration = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'abort' }))
    }
    wsRef.current?.close()
    setIsGenerating(false)
    setShowDrawer(false)
  }, [])

  // Cleanup WebSocket on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close()
      }
    }
  }, [])

  const handleNext = () => {
    if (activeTaskId) {
      navigate(`/task/${activeTaskId}/plan`)
    }
  }

  const isGenerateEnabled = idea.trim().length > 0

  return (
    <div className="min-h-screen" style={{ background: '#f5f6f7' }}>
      {/* Main Container */}
      <div 
        className="max-w-[1100px] mx-auto my-10 p-10 bg-white rounded-[20px] flex flex-col gap-7"
        style={{ boxShadow: '0 10px 30px rgba(17,24,39,.08)' }}
      >
        {/* Top Section */}
        <div className="flex items-start justify-between gap-8">
          {/* Left Panel - Task Management */}
          <div className="flex-shrink-0 w-[35%] min-w-[300px]">
            <div className="text-sm font-bold text-gray-500 mb-3">任务管理</div>
            
            {/* Task List Header */}
            <div className="flex items-center justify-between mb-2.5">
              <div className="font-bold text-gray-500">任务列表</div>
              <button
                onClick={handleNewTask}
                disabled={isCreating || showUploadDialog}
                className="px-3.5 py-2 bg-white border border-gray-200 rounded-[10px] font-semibold hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                {isCreating ? '创建中...' : '＋ 新建任务'}
              </button>
            </div>

            {/* Hidden file inputs */}
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={handleFileSelect}
            />
            <input
              ref={dirInputRef}
              type="file"
              // @ts-ignore - webkitdirectory is not in TypeScript types
              webkitdirectory=""
              // @ts-ignore
              directory=""
              multiple
              className="hidden"
              onChange={handleDirectorySelect}
            />

            {/* Task List */}
            <div className="flex flex-col gap-2 mb-4">
              {loading ? (
                <div className="text-center py-4 text-gray-400">加载中...</div>
              ) : tasks.length === 0 ? (
                <div className="text-center py-4 text-gray-400">暂无任务</div>
              ) : (
                tasks.map((task) => (
                  <div
                    key={task.task_id}
                    onClick={() => handleSelectTask(task)}
                    className={`flex items-center justify-between p-2.5 px-3 rounded-xl border cursor-pointer transition-all ${
                      activeTaskId === task.task_id
                        ? 'bg-[#0f172a] text-white border-[#0f172a]'
                        : 'border-gray-200 hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex-1 truncate">{task.name}</div>
                    <div className="flex gap-2">
                      <button 
                        onClick={(e) => handleDeleteTask(task.task_id, e)}
                        className={`px-2 py-1 rounded text-sm ${
                          activeTaskId === task.task_id 
                            ? 'hover:bg-white/20' 
                            : 'hover:bg-gray-200'
                        }`}
                      >
                        🗑
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Current Task Settings */}
            <div className="text-sm font-bold text-gray-500 mb-3">当前任务设置</div>
            
            <div className="flex flex-col gap-1.5 mb-3">
              <label className="text-xs text-gray-500">任务名称</label>
              <input
                type="text"
                value={taskName}
                onChange={(e) => setTaskName(e.target.value)}
                placeholder="任务名称"
                className="w-full border border-gray-200 bg-gray-50 rounded-xl px-3 py-3 text-sm outline-none focus:border-gray-400"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs text-gray-500">HTML 文件路径</label>
              <input
                type="text"
                value={htmlPath}
                onChange={(e) => setHtmlPath(e.target.value)}
                placeholder="索引.html"
                className="w-full border border-gray-200 bg-gray-50 rounded-xl px-3 py-3 text-sm outline-none focus:border-gray-400"
              />
            </div>
          </div>

          {/* Right Panel - Idea Input */}
          <div className="flex-grow min-w-[400px]">
            <h1 className="text-[40px] font-black mb-2">描述你的想法</h1>
            <p className="text-gray-400 mb-5">AI将帮助你生成完整的演示文稿</p>
            
            <textarea
              value={idea}
              onChange={(e) => setIdea(e.target.value)}
              placeholder="例如：制作一份关于公司2024年度总结的PPT，包括业绩数据、团队成就和未来规划……"
              className="w-full min-h-[200px] border border-gray-200 bg-gray-50 rounded-xl p-3 text-sm outline-none resize-y focus:border-gray-400"
            />

            <div className="flex items-center gap-4 mt-3.5 flex-wrap">
              <button
                onClick={handleGenerate}
                disabled={!isGenerateEnabled}
                className={`px-7 py-3.5 rounded-[14px] font-bold transition-all ${
                  isGenerateEnabled
                    ? 'bg-[#0f172a] text-white shadow-lg hover:bg-[#0b1220] hover:-translate-y-0.5'
                    : 'bg-gray-300 text-white cursor-not-allowed'
                }`}
                style={isGenerateEnabled ? { boxShadow: '0 0 0 8px rgba(15,23,42,.12)' } : {}}
              >
                生成PPT
              </button>

              {/* Quick Templates */}
              <div className="flex gap-4 flex-wrap">
                {Object.keys(QUICK_TEMPLATES).map((template) => (
                  <button
                    key={template}
                    onClick={() => handleQuickTemplate(template)}
                    className="bg-gray-100 px-4 py-2.5 rounded-full text-gray-600 font-bold hover:bg-gray-200 transition-colors"
                  >
                    {template}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between text-gray-400 text-sm mt-2.5">
          <span>提示：内容会在本地保存，便于下次继续。</span>
          <a href="#" className="text-gray-500 hover:text-gray-700">导出当前配置</a>
        </div>
      </div>

      {/* Upload Dialog */}
      {showUploadDialog && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-2xl w-[600px] max-h-[80vh] overflow-hidden flex flex-col shadow-2xl">
            {/* Header */}
            <div className="p-5 border-b border-gray-200">
              <h2 className="text-xl font-bold">选择工作目录或文件</h2>
              <p className="text-gray-500 text-sm mt-1">
                选择一个目录或多个文件作为任务的工作空间
              </p>
            </div>
            
            {/* Content */}
            <div className="p-5 flex-1 overflow-auto">
              {/* Upload Buttons */}
              <div className="flex gap-4 mb-5">
                <button
                  onClick={() => dirInputRef.current?.click()}
                  disabled={isUploading}
                  className="flex-1 py-4 px-6 border-2 border-dashed border-blue-300 rounded-xl bg-blue-50 hover:bg-blue-100 transition-colors flex flex-col items-center gap-2 disabled:opacity-50"
                >
                  <span className="text-3xl">📁</span>
                  <span className="font-semibold text-blue-700">选择目录</span>
                  <span className="text-xs text-gray-500">上传整个文件夹（保持结构）</span>
                </button>
                
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isUploading}
                  className="flex-1 py-4 px-6 border-2 border-dashed border-gray-300 rounded-xl bg-gray-50 hover:bg-gray-100 transition-colors flex flex-col items-center gap-2 disabled:opacity-50"
                >
                  <span className="text-3xl">📄</span>
                  <span className="font-semibold text-gray-700">选择文件</span>
                  <span className="text-xs text-gray-500">选择一个或多个文件</span>
                </button>
              </div>
              
              {/* Selected Files Preview */}
              {selectedFiles.length > 0 && (
                <div className="mb-4">
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-gray-700">
                      已选择 {selectedFiles.length} 个文件
                      {isDirectoryUpload && ' (目录上传)'}
                    </span>
                    <button
                      onClick={() => {
                        setSelectedFiles([])
                        setFilteredFiles([])
                        setIgnoredCount(0)
                        setIgnoreSummary('')
                      }}
                      className="text-sm text-red-500 hover:text-red-700"
                    >
                      清除
                    </button>
                  </div>
                  
                  {/* Filter Summary */}
                  {ignoredCount > 0 && (
                    <div className="mb-2 p-2 bg-yellow-50 border border-yellow-200 rounded-lg text-sm">
                      <div className="flex items-center gap-2">
                        <span className="text-yellow-600">⚠️</span>
                        <span className="text-yellow-700">
                          将上传 <strong>{filteredFiles.length}</strong> 个文件，
                          已过滤 <strong>{ignoredCount}</strong> 个文件
                        </span>
                      </div>
                      {ignoreSummary && (
                        <div className="text-xs text-yellow-600 mt-1">
                          {ignoreSummary}
                        </div>
                      )}
                    </div>
                  )}
                  
                  <div className="bg-gray-50 rounded-lg p-3 max-h-40 overflow-auto">
                    {filteredFiles.slice(0, 20).map((file, index) => (
                      <div key={index} className="text-sm text-gray-600 py-0.5 flex justify-between">
                        <span className="truncate flex-1">
                          {isDirectoryUpload
                            ? (file as any).webkitRelativePath || file.name
                            : file.name}
                        </span>
                        <span className="text-gray-400 ml-2 flex-shrink-0">
                          {formatFileSize(file.size)}
                        </span>
                      </div>
                    ))}
                    {filteredFiles.length > 20 && (
                      <div className="text-sm text-gray-400 pt-1">
                        ... 还有 {filteredFiles.length - 20} 个文件
                      </div>
                    )}
                    {filteredFiles.length === 0 && selectedFiles.length > 0 && (
                      <div className="text-sm text-gray-400 py-2 text-center">
                        所有文件都被过滤了（.gitignore 规则）
                      </div>
                    )}
                  </div>
                  
                  {/* Upload Button */}
                  <button
                    onClick={handleUpload}
                    disabled={isUploading || filteredFiles.length === 0}
                    className="mt-3 w-full py-2.5 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isUploading ? '上传中...' : `上传 ${filteredFiles.length} 个文件`}
                  </button>
                </div>
              )}
              
              {/* Upload Progress */}
              {uploadProgress && (
                <div className={`text-sm py-2 px-3 rounded-lg mb-4 ${
                  uploadProgress.includes('失败')
                    ? 'bg-red-50 text-red-600'
                    : 'bg-green-50 text-green-600'
                }`}>
                  {uploadProgress}
                </div>
              )}
              
              {/* Uploaded Files List */}
              {uploadedFiles.length > 0 && (
                <div>
                  <div className="font-semibold text-gray-700 mb-2">
                    工作空间中的文件 ({uploadedFiles.length})
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3 max-h-40 overflow-auto">
                    {uploadedFiles.map((file, index) => (
                      <div key={index} className="text-sm text-gray-600 py-0.5 flex justify-between">
                        <span className="truncate flex-1">📄 {file.path}</span>
                        <span className="text-gray-400 ml-2 flex-shrink-0">
                          {formatFileSize(file.size)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            
            {/* Footer */}
            <div className="p-5 border-t border-gray-200 flex justify-end gap-3">
              <button
                onClick={handleCancelNewTask}
                className="px-5 py-2.5 border border-gray-200 rounded-lg font-semibold hover:bg-gray-50 transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleConfirmTask}
                disabled={uploadedFiles.length === 0}
                className="px-5 py-2.5 bg-[#0f172a] text-white rounded-lg font-semibold hover:bg-[#0b1220] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                确认创建
              </button>
            </div>
            
            {/* Warning if files selected but not uploaded */}
            {filteredFiles.length > 0 && uploadedFiles.length === 0 && (
              <div className="px-5 pb-3 -mt-2">
                <p className="text-sm text-orange-600">
                  ⚠️ 请先点击上方的"上传"按钮将文件上传到服务器
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Drawer Backdrop */}
      <div
        className={`fixed inset-0 bg-black/35 transition-opacity z-[39] ${
          showDrawer ? 'opacity-100' : 'opacity-0 pointer-events-none'
        }`}
        onClick={() => {
          // Don't close drawer while generating
          if (!isGenerating) {
            setShowDrawer(false)
          }
        }}
      />

      {/* Drawer */}
      <aside 
        className={`fixed top-0 right-0 h-screen w-[min(560px,92vw)] bg-white border-l border-gray-200 flex flex-col z-40 transition-transform duration-300 ${
          showDrawer ? 'translate-x-0' : 'translate-x-full'
        }`}
        style={{ boxShadow: '-20px 0 40px rgba(0,0,0,.08)' }}
      >
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <div className="font-extrabold">生成预览</div>
          <button 
            onClick={() => setShowDrawer(false)}
            className="px-3.5 py-2 bg-white border border-gray-200 rounded-[10px] font-semibold hover:bg-gray-50"
          >
            关闭
          </button>
        </div>
        
        <div className="flex-1 p-4 overflow-auto flex flex-col">
          {/* Always show streaming content if we have any, or if generating */}
          {(isGenerating || streamingContent) ? (
            <div className="space-y-4 flex-1 flex flex-col">
              <div className="flex items-center gap-3">
                {isGenerating ? (
                  <div className="animate-spin w-5 h-5 border-2 border-gray-300 border-t-gray-600 rounded-full"></div>
                ) : (
                  <div className="w-5 h-5 bg-green-500 rounded-full flex items-center justify-center text-white text-xs">✓</div>
                )}
                <span className="text-gray-600 font-medium">
                  {isGenerating ? 'AI 正在生成演示文稿规划...' : '生成完成'}
                </span>
              </div>
              
              <div className="bg-gray-50 rounded-lg p-3 text-sm">
                <p className="text-gray-500">
                  当前阶段: <span className="font-medium text-gray-700">{currentPhase}</span>
                </p>
                <p className="text-gray-500 mt-1">
                  状态: <span className={`font-medium ${isGenerating ? 'text-green-600' : 'text-blue-600'}`}>
                    {isGenerating ? '实时流式输出' : '已完成'}
                  </span>
                </p>
              </div>
              
              {/* Streaming content display - always show if we have content */}
              <div
                ref={streamingContentRef}
                className="flex-1 bg-gray-900 rounded-lg p-4 font-mono text-sm text-green-400 overflow-auto min-h-[200px] max-h-[400px] whitespace-pre-wrap"
              >
                {streamingContent || '等待 AI 响应...'}
                {isGenerating && <span className="animate-pulse">▌</span>}
              </div>
              
              {isGenerating ? (
                <p className="text-gray-400 text-xs">AI 正在实时生成内容，请耐心等待...</p>
              ) : generationStatus?.plan_ready ? (
                <div className="bg-green-50 border border-green-200 rounded-lg p-3">
                  <p className="text-green-700 font-medium">✓ 演示文稿框架提纲已生成！</p>
                  <p className="text-green-600 text-sm mt-1">请点击下方「前往编辑」按钮继续。</p>
                </div>
              ) : streamingContent ? (
                <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
                  <p className="text-yellow-700 font-medium">生成完成</p>
                  <p className="text-yellow-600 text-sm mt-1">未能创建完整的框架提纲，请查看上方输出内容。</p>
                </div>
              ) : null}
            </div>
          ) : generationError ? (
            <div className="space-y-4">
              <div className="bg-red-50 border border-red-200 rounded-lg p-3">
                <p className="text-red-600 font-medium">生成失败</p>
                <p className="text-red-500 text-sm mt-1">{generationError}</p>
              </div>
              <button
                onClick={() => {
                  setGenerationError(null)
                  handleGenerate()
                }}
                className="px-4 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm font-medium"
              >
                重试
              </button>
            </div>
          ) : (
            <>
              <p className="text-gray-500 mb-4">AI 将分析你的想法并生成演示文稿规划。</p>
              <div className="border border-dashed border-gray-200 rounded-xl p-3">
                <p className="text-sm text-gray-400 mb-2">你的想法：</p>
                {idea.length > 240 ? idea.slice(0, 240) + '…' : idea}
              </div>
            </>
          )}
        </div>

        <div className="flex gap-2.5 p-3.5 border-t border-gray-200 justify-end">
          {isGenerating ? (
            <button
              onClick={handleCancelGeneration}
              className="px-3.5 py-2 bg-red-500 text-white rounded-[10px] font-semibold hover:bg-red-600"
            >
              取消生成
            </button>
          ) : (
            <>
              <button
                onClick={() => {
                  setShowDrawer(false)
                  setGenerationError(null)
                  setStreamingContent('')
                  setGenerationStatus(null)
                }}
                className="px-3.5 py-2 bg-white border border-gray-200 rounded-[10px] font-semibold hover:bg-gray-50"
              >
                关闭
              </button>
              {generationStatus?.plan_ready && (
                <button
                  onClick={handleNext}
                  className="px-3.5 py-2 bg-green-600 text-white rounded-[10px] font-semibold hover:bg-green-700 animate-pulse"
                >
                  前往编辑 →
                </button>
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  )
}