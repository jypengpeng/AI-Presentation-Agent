import { Routes, Route, Navigate } from 'react-router-dom'
import TaskListPage from './pages/TaskListPage'
import PlanEditorPage from './pages/PlanEditorPage'
import GenerationPage from './pages/GenerationPage'
import SlideEditorPage from './pages/SlideEditorPage'
import Layout from './components/Layout'

function App() {
  return (
    <Layout>
      <Routes>
        {/* Phase 1: Collecting - Task list and idea input */}
        <Route path="/" element={<TaskListPage />} />
        
        {/* Phase 2: Editing Plan - Outline editor */}
        <Route path="/task/:taskId/plan" element={<PlanEditorPage />} />
        
        {/* Phase 3: Designing - Generation progress */}
        <Route path="/task/:taskId/generate" element={<GenerationPage />} />
        
        {/* Phase 4: Slide Editor - Individual slide editing */}
        <Route path="/task/:taskId/slides" element={<SlideEditorPage />} />
        <Route path="/task/:taskId/slides/:slideIndex" element={<SlideEditorPage />} />
        
        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}

export default App