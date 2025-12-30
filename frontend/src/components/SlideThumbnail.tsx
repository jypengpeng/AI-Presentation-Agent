import { DetailedSlide } from '../types'

type GenerationStatus = 'queued' | 'running' | 'done' | 'failed'

interface SlideThumbnailProps {
  slide: DetailedSlide
  index: number
  isActive: boolean
  onClick: () => void
  status?: GenerationStatus
  htmlContent?: string
  htmlUrl?: string  // Alternative: load from URL instead of content
  streamingContent?: string
}

export default function SlideThumbnail({
  slide,
  index,
  isActive,
  onClick,
  status = 'queued',
  htmlContent,
  htmlUrl,
  streamingContent
}: SlideThumbnailProps) {
  // Status badge configuration
  const statusConfig = {
    queued: { label: '待生成', bg: 'bg-gray-100', text: 'text-gray-500', icon: '⏳' },
    running: { label: '生成中', bg: 'bg-yellow-100', text: 'text-yellow-700', icon: '⚙️' },
    done: { label: '已完成', bg: 'bg-green-100', text: 'text-green-700', icon: '✓' },
    failed: { label: '失败', bg: 'bg-red-100', text: 'text-red-700', icon: '✕' }
  }

  const currentStatus = statusConfig[status]

  return (
    <div
      onClick={onClick}
      className={`mb-3 cursor-pointer transition-all group ${
        isActive ? 'scale-[1.02]' : 'hover:scale-[1.01]'
      }`}
    >
      <div className={`relative rounded-xl overflow-hidden border-2 transition-all ${
        isActive
          ? 'border-black shadow-lg'
          : 'border-gray-200 hover:border-gray-300'
      }`}>
        {/* Thumbnail Preview */}
        <div className="aspect-[16/9] bg-white overflow-hidden">
          {status === 'done' && (htmlContent || htmlUrl) ? (
            // Show HTML thumbnail preview - use srcDoc if content available, else src
            <div className="w-full h-full relative overflow-hidden">
              <iframe
                {...(htmlContent ? { srcDoc: htmlContent } : { src: htmlUrl })}
                className="absolute top-0 left-0 pointer-events-none border-0"
                style={{
                  width: '1920px',
                  height: '1080px',
                  transform: 'scale(0.1)',
                  transformOrigin: 'top left'
                }}
                sandbox="allow-same-origin allow-scripts"
                title={`Slide ${index + 1} preview`}
              />
            </div>
          ) : status === 'running' ? (
            // Show generating animation
            <div className="w-full h-full flex flex-col items-center justify-center bg-gradient-to-br from-yellow-50 to-orange-50">
              <span className="text-2xl animate-spin mb-1">⚙️</span>
              <span className="text-[8px] text-yellow-600 font-medium">生成中...</span>
              {streamingContent && (
                <div className="mt-1 px-2 w-full">
                  <div className="text-[6px] text-gray-400 truncate">
                    {streamingContent.slice(0, 50)}...
                  </div>
                </div>
              )}
            </div>
          ) : status === 'failed' ? (
            // Show failed state
            <div className="w-full h-full flex flex-col items-center justify-center bg-red-50">
              <span className="text-2xl mb-1">❌</span>
              <span className="text-[8px] text-red-500 font-medium">生成失败</span>
            </div>
          ) : (
            // Show queued/waiting state
            <div className="w-full h-full p-3 flex flex-col">
              <div className="text-[8px] font-bold text-gray-800 truncate mb-1">
                {slide.title || '无标题'}
              </div>
              <div className="text-[6px] text-gray-400 truncate">
                {slide.subtitle || ''}
              </div>
              <div className="flex-1 flex items-center justify-center mt-2">
                <div className="w-full h-full bg-gray-50 rounded flex items-center justify-center">
                  <span className="text-gray-300 text-lg">📄</span>
                </div>
              </div>
            </div>
          )}
        </div>
        
        {/* Slide Number */}
        <div className={`absolute bottom-2 left-2 text-[10px] font-bold px-1.5 py-0.5 rounded ${
          isActive
            ? 'bg-black text-white'
            : 'bg-gray-100 text-gray-500'
        }`}>
          {index + 1}
        </div>

        {/* Status Badge */}
        {status !== 'done' && (
          <div className={`absolute top-2 right-2 text-[8px] font-medium px-1.5 py-0.5 rounded flex items-center gap-1 ${currentStatus.bg} ${currentStatus.text}`}>
            <span className={status === 'running' ? 'animate-spin' : ''}>{currentStatus.icon}</span>
            <span className="hidden group-hover:inline">{currentStatus.label}</span>
          </div>
        )}
      </div>
    </div>
  )
}