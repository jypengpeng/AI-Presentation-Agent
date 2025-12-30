import { Slide } from '../types'

interface SlideEditorCardProps {
  slide: Slide
  index: number
  onUpdate: (slide: Slide) => void
  onRemove: () => void
  onMoveUp?: () => void
  onMoveDown?: () => void
}

export default function SlideEditorCard({
  slide,
  index,
  onUpdate,
  onRemove,
  onMoveUp,
  onMoveDown
}: SlideEditorCardProps) {
  return (
    <div className="bg-white p-8 rounded-[2rem] border border-neutral-100 shadow-sm relative group hover:shadow-md transition-all">
      {/* Slide Number Badge */}
      <div className="absolute -left-3 top-8 w-8 h-8 bg-neutral-900 text-white rounded-xl flex items-center justify-center text-xs font-bold shadow-lg">
        {index + 1}
      </div>
      
      {/* Actions */}
      <div className="absolute right-6 top-6 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
        {onMoveUp && (
          <button 
            onClick={onMoveUp}
            className="w-8 h-8 flex items-center justify-center rounded-lg border border-neutral-200 hover:bg-neutral-50 transition-colors text-neutral-400 hover:text-neutral-600"
            title="上移"
          >
            ↑
          </button>
        )}
        {onMoveDown && (
          <button 
            onClick={onMoveDown}
            className="w-8 h-8 flex items-center justify-center rounded-lg border border-neutral-200 hover:bg-neutral-50 transition-colors text-neutral-400 hover:text-neutral-600"
            title="下移"
          >
            ↓
          </button>
        )}
        <button 
          onClick={onRemove}
          className="w-8 h-8 flex items-center justify-center rounded-lg border border-red-200 hover:bg-red-50 transition-colors text-red-400 hover:text-red-600"
          title="删除"
        >
          ×
        </button>
      </div>

      {/* Type Selector */}
      <div className="mb-6">
        <label className="text-[10px] font-bold text-neutral-300 uppercase tracking-[0.3em] mb-2 block">
          页面类型
        </label>
        <div className="flex gap-2">
          {(['title', 'content', 'section', 'end'] as const).map((type) => (
            <button
              key={type}
              onClick={() => onUpdate({ ...slide, type })}
              className={`px-4 py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider transition-all ${
                slide.type === type
                  ? 'bg-neutral-900 text-white'
                  : 'bg-neutral-50 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-600'
              }`}
            >
              {type === 'title' ? '标题页' : 
               type === 'content' ? '内容页' : 
               type === 'section' ? '章节页' : '结束页'}
            </button>
          ))}
        </div>
      </div>

      {/* Title Input */}
      <div className="mb-4">
        <label className="text-[10px] font-bold text-neutral-300 uppercase tracking-[0.3em] mb-2 block">
          页面标题
        </label>
        <input
          type="text"
          value={slide.title}
          onChange={(e) => onUpdate({ ...slide, title: e.target.value })}
          placeholder="请输入页面标题..."
          className="w-full text-xl font-bold bg-transparent border-b-2 border-neutral-100 focus:border-neutral-900 outline-none pb-2 transition-colors placeholder:text-neutral-200"
        />
      </div>

      {/* Content Textarea */}
      <div>
        <label className="text-[10px] font-bold text-neutral-300 uppercase tracking-[0.3em] mb-2 block">
          页面内容
        </label>
        <textarea
          value={slide.content}
          onChange={(e) => onUpdate({ ...slide, content: e.target.value })}
          placeholder="请输入页面内容要点..."
          rows={4}
          className="w-full bg-neutral-50 rounded-xl p-4 text-sm text-neutral-700 outline-none resize-none border border-neutral-100 focus:border-neutral-300 transition-colors placeholder:text-neutral-300"
        />
      </div>

      {/* Notes (optional) */}
      <div className="mt-4 pt-4 border-t border-neutral-50">
        <label className="text-[10px] font-bold text-neutral-200 uppercase tracking-[0.3em] mb-2 block">
          演讲备注（可选）
        </label>
        <textarea
          value={slide.notes || ''}
          onChange={(e) => onUpdate({ ...slide, notes: e.target.value })}
          placeholder="添加演讲者备注..."
          rows={2}
          className="w-full bg-transparent text-xs text-neutral-400 outline-none resize-none placeholder:text-neutral-200"
        />
      </div>
    </div>
  )
}