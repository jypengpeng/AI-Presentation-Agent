import { Task, Presentation, GenerationProgress } from '../types'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Upload result types
export interface UploadResult {
  success: boolean
  task_id: string
  files_uploaded: number
  total_size_bytes: number
  message: string
}

export interface FileInfo {
  path: string
  size: number
}

export interface UploadSummary {
  task_id: string
  total_files: number
  total_size_bytes: number
  files: FileInfo[]
}

// Helper function for API calls
async function fetchAPI<T>(
  endpoint: string, 
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  })
  
  if (!response.ok) {
    throw new Error(`API Error: ${response.statusText}`)
  }
  
  return response.json()
}

// Task APIs
export async function getTasks(): Promise<Task[]> {
  const response = await fetchAPI<{ tasks: any[], total: number }>('/tasks')
  return response.tasks.map(t => ({
    task_id: t.id,
    name: t.name,
    phase: t.phase,
    status: t.status,
    slides_count: t.slide_count || 0,
    created_at: t.created_at,
    updated_at: t.updated_at
  }))
}

export async function getTask(taskId: string): Promise<Task> {
  const t = await fetchAPI<any>(`/tasks/${taskId}`)
  return {
    task_id: t.id,
    name: t.name,
    phase: t.phase,
    status: t.status,
    slides_count: t.slide_count || 0,
    created_at: t.created_at,
    updated_at: t.updated_at
  }
}

export async function createTask(name: string): Promise<Task> {
  const t = await fetchAPI<any>('/tasks', {
    method: 'POST',
    body: JSON.stringify({ name }),
  })
  return {
    task_id: t.id,
    name: t.name,
    phase: t.phase,
    status: t.status,
    slides_count: t.slide_count || 0,
    created_at: t.created_at,
    updated_at: t.updated_at
  }
}

export async function deleteTask(taskId: string): Promise<void> {
  await fetchAPI(`/tasks/${taskId}`, {
    method: 'DELETE',
  })
}

export async function updateTaskPhase(
  taskId: string,
  phase: string
): Promise<Task> {
  const t = await fetchAPI<any>(`/tasks/${taskId}/transition?target_phase=${phase}`, {
    method: 'POST',
  })
  return {
    task_id: t.id,
    name: t.name,
    phase: t.phase,
    status: t.status,
    slides_count: t.slide_count || 0,
    created_at: t.created_at,
    updated_at: t.updated_at
  }
}

// Idea/Content APIs
export async function submitIdea(
  taskId: string,
  idea: string
): Promise<{ success: boolean }> {
  // Store idea in task metadata
  await fetchAPI(`/tasks/${taskId}`, {
    method: 'PATCH',
    body: JSON.stringify({ metadata: { idea } }),
  })
  return { success: true }
}

// Agent APIs - Start AI generation
export interface AgentRunResponse {
  success: boolean
  task_id: string
  message: string
  phase: string
}

export interface AgentStatus {
  status: 'idle' | 'running' | 'completed' | 'error'
  phase: string | null
  messages?: Array<{ role: string; content: string }>
  error?: string
  plan_exists?: boolean
  plan_ready?: boolean
  task_phase?: string
}

export async function startAgentGeneration(
  taskId: string,
  idea: string,
  phase?: string
): Promise<AgentRunResponse> {
  return fetchAPI<AgentRunResponse>(`/tasks/${taskId}/agent/run`, {
    method: 'POST',
    body: JSON.stringify({ message: idea, phase }),
  })
}

export async function getAgentStatus(taskId: string): Promise<AgentStatus> {
  return fetchAPI<AgentStatus>(`/tasks/${taskId}/agent/status`)
}

// Plan APIs
export async function getPlan(taskId: string): Promise<Presentation> {
  return fetchAPI<Presentation>(`/tasks/${taskId}/slides/plan`)
}

export async function savePlan(
  taskId: string,
  plan: Presentation
): Promise<Presentation> {
  return fetchAPI<Presentation>(`/tasks/${taskId}/slides/plan`, {
    method: 'PUT',
    body: JSON.stringify(plan),
  })
}

export async function generatePlan(
  taskId: string,
  prompt: string
): Promise<Presentation> {
  return fetchAPI<Presentation>(`/tasks/${taskId}/slides/plan/generate`, {
    method: 'POST',
    body: JSON.stringify({ prompt }),
  })
}

// Generation APIs
export async function startGeneration(
  taskId: string
): Promise<{ success: boolean }> {
  return fetchAPI(`/tasks/${taskId}/slides/generate`, {
    method: 'POST',
  })
}

export async function getGenerationProgress(
  taskId: string
): Promise<GenerationProgress> {
  return fetchAPI<GenerationProgress>(`/tasks/${taskId}/slides/generate/progress`)
}

export async function regenerateSlide(
  taskId: string,
  slideId: string
): Promise<{ success: boolean }> {
  return fetchAPI(`/tasks/${taskId}/slides/${slideId}/regenerate`, {
    method: 'POST',
  })
}

// Slide APIs
export async function getSlide(
  taskId: string,
  slideIndex: number
): Promise<any> {
  return fetchAPI(`/tasks/${taskId}/slides/${slideIndex}`)
}

export async function updateSlide(
  taskId: string,
  slideIndex: number,
  content: any
): Promise<any> {
  return fetchAPI(`/tasks/${taskId}/slides/${slideIndex}`, {
    method: 'PATCH',
    body: JSON.stringify(content),
  })
}

// AI Modify types
export interface AIModifyResponse {
  success: boolean
  message: string
  slide_updated: boolean
}

export interface AIMessage {
  role: 'user' | 'assistant'
  content: string
}

export async function modifySlideWithAI(
  taskId: string,
  slideIndex: number,
  prompt: string,
  context?: AIMessage[]
): Promise<AIModifyResponse> {
  return fetchAPI<AIModifyResponse>(`/tasks/${taskId}/slides/${slideIndex}/ai-modify`, {
    method: 'POST',
    body: JSON.stringify({ prompt, context }),
  })
}

// Export APIs
export function getExportUrl(
  taskId: string,
  format: 'html' | 'pptx' | 'zip'
): string {
  return `${API_BASE}/tasks/${taskId}/slides/export/${format}`
}

// Get slide HTML URL for preview
export function getSlideHtmlUrl(taskId: string, slideIndex: number): string {
  // Use /api prefix so Vite proxy can handle it in dev mode
  // In production with nginx, this will also work
  return `/api/tasks/${taskId}/slides/${slideIndex}/html`
}

// Upload APIs

/**
 * Upload files to a task's workspace.
 *
 * @param taskId - Target task ID
 * @param files - Array of File objects
 * @param relativePaths - Optional array of relative paths for each file
 * @returns Upload result
 */
export async function uploadFiles(
  taskId: string,
  files: File[],
  relativePaths?: string[]
): Promise<UploadResult> {
  console.log('[API Upload] uploadFiles called')
  console.log('[API Upload] taskId:', taskId)
  console.log('[API Upload] files count:', files.length)
  console.log('[API Upload] relativePaths provided:', !!relativePaths)
  if (relativePaths) {
    console.log('[API Upload] relativePaths count:', relativePaths.length)
    console.log('[API Upload] sample paths:', relativePaths.slice(0, 3))
  }
  
  const formData = new FormData()
  
  files.forEach((file, index) => {
    formData.append('files', file)
    if (index < 3) {
      console.log(`[API Upload] Appending file ${index}: name=${file.name}, size=${file.size}`)
    }
  })
  
  if (relativePaths && relativePaths.length > 0) {
    const pathsJson = JSON.stringify(relativePaths)
    console.log('[API Upload] Appending paths JSON (length):', pathsJson.length)
    formData.append('paths', pathsJson)
  }
  
  console.log('[API Upload] Sending request to:', `${API_BASE}/upload/${taskId}/files`)
  
  const response = await fetch(`${API_BASE}/upload/${taskId}/files`, {
    method: 'POST',
    body: formData,
  })
  
  console.log('[API Upload] Response status:', response.status, response.statusText)
  
  if (!response.ok) {
    const errorText = await response.text()
    console.error('[API Upload] Error response:', errorText)
    throw new Error(`Upload failed: ${response.statusText}`)
  }
  
  const result = await response.json()
  console.log('[API Upload] Success result:', result)
  return result
}

/**
 * Upload a directory (multiple files with relative paths) to a task's workspace.
 *
 * @param taskId - Target task ID
 * @param files - Array of File objects from directory input
 * @param basePath - Optional base path to prepend
 * @returns Upload result
 */
export async function uploadDirectory(
  taskId: string,
  files: File[],
  basePath?: string
): Promise<UploadResult> {
  const formData = new FormData()
  
  files.forEach((file) => {
    // For directory uploads, the webkitRelativePath contains the full relative path
    formData.append('files', file)
  })
  
  if (basePath) {
    formData.append('base_path', basePath)
  }
  
  const response = await fetch(`${API_BASE}/upload/${taskId}/directory`, {
    method: 'POST',
    body: formData,
  })
  
  if (!response.ok) {
    throw new Error(`Upload failed: ${response.statusText}`)
  }
  
  return response.json()
}

/**
 * List all uploaded files in a task's workspace.
 *
 * @param taskId - Task ID
 * @returns Upload summary with file list
 */
export async function listUploadedFiles(
  taskId: string
): Promise<UploadSummary> {
  return fetchAPI<UploadSummary>(`/upload/${taskId}/files`)
}

/**
 * Clear all files in a task's workspace.
 *
 * @param taskId - Task ID
 * @returns Success message
 */
export async function clearWorkspace(
  taskId: string
): Promise<{ message: string }> {
  return fetchAPI(`/upload/${taskId}/files`, {
    method: 'DELETE',
  })
}

/**
 * Delete a specific file from workspace.
 *
 * @param taskId - Task ID
 * @param filePath - Relative path to the file
 * @returns Success message
 */
export async function deleteUploadedFile(
  taskId: string,
  filePath: string
): Promise<{ message: string }> {
  return fetchAPI(`/upload/${taskId}/files/${encodeURIComponent(filePath)}`, {
    method: 'DELETE',
  })
}