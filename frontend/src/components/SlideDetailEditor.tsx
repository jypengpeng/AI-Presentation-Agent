import { DetailedSlide, SlideContentItem } from '../types'

interface SlideDetailEditorProps {
  slide: DetailedSlide
  onUpdate: (slide: DetailedSlide) => void
}

export default function SlideDetailEditor({
  slide,
  onUpdate
}: SlideDetailEditorProps) {
  const handleTitleChange = (title: string) => {
    onUpdate({ ...slide, title })
  }

  const handleSubtitleChange = (subtitle: string) => {
    onUpdate({ ...slide, subtitle })
  }

  const handleLayoutChange = (layout: DetailedSlide['layout']) => {
    onUpdate({ ...slide, layout })
  }

  const handleContentItemChange = (id: string, field: 'label' | 'value', value: string) => {
    onUpdate({
      ...slide,
      content: slide.content.map(item =>
        item.id === id ? { ...item, [field]: value } : item
      )
    })
  }

  const handleAddContentItem = () => {
    const newItem: SlideContentItem = {
      id: `c-${Date.now()}`,
      label: '新要点',
      value: ''
    }
    onUpdate({
      ...slide,
      content: [...slide.content, newItem]
    })
  }

  const handleRemoveContentItem = (id: string) => {
    if (slide.content.length <= 1) return
    onUpdate({
      ...slide,
      content: slide.content.filter(item => item.id !== id)
    })
  }

  return (
    <div className="flex-1 p-8 overflow-auto">
      {/* Slide Preview Card */}
      <div className="max-w-4xl mx-auto">
        <div className="bg-white rounded-3xl shadow-xl border border-gray-100 overflow-hidden">
          {/* Slide Content */}
          <div className="aspect-[16/9] bg-gradient-to-br from-gray-50 to-white p-12 flex flex-col">
            {/* Title */}
            <input
              type="text"
              value={slide.title}
              onChange={(e) => handleTitleChange(e.target.value)}
              placeholder="幻灯片标题"
              className="text-4xl font-black text-gray-900 bg-transparent border-none outline-none mb-4 placeholder:text-gray-200"
            />
            
            {/* Subtitle */}
            <input
              type="text"
              value={slide.subtitle || ''}
              onChange={(e) => handleSubtitleChange(e.target.value)}
              placeholder="副标题（可选）"
              className="text-lg text-gray-500 bg-transparent border-none outline-none mb-8 placeholder:text-gray-200"
            />

            {/* Content Items */}
            <div className={`flex-1 ${
              slide.layout === 'grid' 
                ? 'grid grid-cols-2 gap-6' 
                : 'space-y-4'
            }`}>
              {slide.content.map((item, index) => (
                <div 
                  key={item.id}
                  className={`group relative ${
                    slide.layout === 'minimal' 
                      ? 'border-l-4 border-gray-900 pl-4' 
                      : 'bg-white rounded-xl p-4 shadow-sm border border-gray-100'
                  }`}
                >
                  {/* Remove Button */}
                  <button
                    onClick={() => handleRemoveContentItem(item.id)}
                    className="absolute -top-2 -right-2 w-6 h-6 bg-red-500 text-white rounded-full text-xs opacity-0 group-hover:opacity-100 transition-opacity shadow-md"
                  >
                    ×
                  </button>
                  
                  {/* Label */}
                  <input
                    type="text"
                    value={item.label}
                    onChange={(e) => handleContentItemChange(item.id, 'label', e.target.value)}
                    placeholder="要点标题"
                    className="text-sm font-bold text-gray-800 bg-transparent border-none outline-none mb-1 w-full placeholder:text-gray-300"
                  />
                  
                  {/* Value */}
                  <textarea
                    value={item.value}
                    onChange={(e) => handleContentItemChange(item.id, 'value', e.target.value)}
                    placeholder="要点内容..."
                    rows={2}
                    className="text-sm text-gray-600 bg-transparent border-none outline-none resize-none w-full placeholder:text-gray-300"
                  />
                </div>
              ))}

              {/* Add Content Item Button */}
              <button
                onClick={handleAddContentItem}
                className="border-2 border-dashed border-gray-200 rounded-xl p-4 text-gray-400 hover:border-gray-400 hover:text-gray-600 transition-colors flex items-center justify-center gap-2"
              >
                <span>➕</span>
                <span className="text-sm font-medium">添加内容块</span>
              </button>
            </div>
          </div>

          {/* Slide Footer */}
          <div className="p-4 bg-gray-50 border-t border-gray-100 flex items-center justify-between text-xs text-gray-400">
            <div className="flex items-center gap-2">
              <span>📄</span>
              <span className="font-mono">{slide.id}</span>
            </div>
            <div className="flex items-center gap-4">
              <span>布局: {slide.layout}</span>
              <span>内容块: {slide.content.length}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}