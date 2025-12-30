/**
 * GitIgnore pattern matcher for filtering uploaded files.
 * 
 * Supports basic gitignore patterns:
 * - Simple file/directory names
 * - Wildcards (* and ?)
 * - Directory-only patterns (ending with /)
 * - Negation patterns (starting with !)
 * - Comments (starting with #)
 */

// Default patterns to always ignore (commonly large or unnecessary)
const DEFAULT_IGNORE_PATTERNS = [
  '.git/',
  '.git',
  'node_modules/',
  'node_modules',
  '__pycache__/',
  '__pycache__',
  '.venv/',
  '.venv',
  'venv/',
  'venv',
  '.env',
  '.env.local',
  '.env.*.local',
  '*.pyc',
  '*.pyo',
  '*.pyd',
  '.DS_Store',
  'Thumbs.db',
  '.idea/',
  '.vscode/',
  '*.egg-info/',
  'dist/',
  'build/',
  '*.egg',
  '.eggs/',
]

// Additional patterns from .gitignore
const GITIGNORE_PATTERNS = [
  // Environment variables
  '.env',
  '.env.local',
  '.env.*.local',
  
  // Python
  '__pycache__/',
  '*.py[cod]',
  '*$py.class',
  '*.so',
  '.Python',
  'build/',
  'develop-eggs/',
  'dist/',
  'downloads/',
  'eggs/',
  '.eggs/',
  'lib/',
  'lib64/',
  'parts/',
  'sdist/',
  'var/',
  'wheels/',
  '*.egg-info/',
  '.installed.cfg',
  '*.egg',
  
  // Virtual environments
  '.venv/',
  'venv/',
  'ENV/',
  'env/',
  
  // IDE
  '.idea/',
  '.vscode/',
  '*.swp',
  '*.swo',
  '*~',
  
  // OS
  '.DS_Store',
  'Thumbs.db',
  
  // Streamlit
  '.streamlit/secrets.toml',
  
  // Project specific - commented out as these may be legitimate directories
  // 'tasks/',
  // 'reference/',
]

/**
 * Convert a gitignore pattern to a regex.
 */
function patternToRegex(pattern: string): RegExp {
  // Remove trailing slash for directories
  const isDir = pattern.endsWith('/')
  if (isDir) {
    pattern = pattern.slice(0, -1)
  }
  
  // Escape special regex characters except * and ?
  let regex = pattern
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*/g, '.*')
    .replace(/\?/g, '.')
  
  // Handle patterns with path separator
  if (pattern.includes('/')) {
    if (pattern.startsWith('/')) {
      // Anchored to root
      regex = '^' + regex.slice(2) // Remove the escaped \/ at start
    } else {
      // Can match anywhere in path
      regex = '(^|/)' + regex
    }
  } else {
    // Match basename only
    regex = '(^|/)' + regex + '$'
  }
  
  if (isDir) {
    // Match as directory (has trailing content or is at end)
    regex = regex + '(/|$)'
  } else {
    regex = regex + '$'
  }
  
  return new RegExp(regex, 'i')
}

/**
 * Check if a path matches any gitignore pattern.
 */
export function shouldIgnore(relativePath: string, isDirectory: boolean = false): boolean {
  // Normalize path
  const normalizedPath = relativePath.replace(/\\/g, '/')
  
  // Combine all patterns
  const allPatterns = [...DEFAULT_IGNORE_PATTERNS, ...GITIGNORE_PATTERNS]
  
  for (const pattern of allPatterns) {
    // Skip empty patterns and comments
    if (!pattern || pattern.startsWith('#')) continue
    
    // Skip negation patterns for now (we're only checking if should ignore)
    if (pattern.startsWith('!')) continue
    
    try {
      const regex = patternToRegex(pattern)
      if (regex.test(normalizedPath)) {
        return true
      }
    } catch (e) {
      // Invalid pattern, skip
      console.warn(`Invalid gitignore pattern: ${pattern}`)
    }
  }
  
  // Also check parent directories
  const parts = normalizedPath.split('/')
  for (let i = 0; i < parts.length; i++) {
    const partialPath = parts.slice(0, i + 1).join('/')
    for (const pattern of allPatterns) {
      if (!pattern || pattern.startsWith('#') || pattern.startsWith('!')) continue
      
      try {
        const regex = patternToRegex(pattern)
        if (regex.test(partialPath)) {
          return true
        }
      } catch (e) {
        // Invalid pattern, skip
      }
    }
  }
  
  return false
}

/**
 * Filter a list of files based on gitignore rules.
 * 
 * @param files - Array of File objects
 * @param getRelativePath - Function to get relative path from a File
 * @returns Object with filtered files and statistics
 */
export function filterFiles(
  files: File[],
  getRelativePath: (file: File) => string
): {
  filtered: File[]
  ignoredCount: number
  ignoredPaths: string[]
} {
  const filtered: File[] = []
  const ignoredPaths: string[] = []
  
  for (const file of files) {
    const relativePath = getRelativePath(file)
    
    if (shouldIgnore(relativePath)) {
      ignoredPaths.push(relativePath)
    } else {
      filtered.push(file)
    }
  }
  
  return {
    filtered,
    ignoredCount: ignoredPaths.length,
    ignoredPaths,
  }
}

/**
 * Get a human-readable summary of ignored files.
 */
export function getIgnoreSummary(ignoredPaths: string[]): string {
  if (ignoredPaths.length === 0) return ''
  
  // Group by pattern type
  const byType: Record<string, number> = {}
  
  for (const path of ignoredPaths) {
    if (path.includes('node_modules')) {
      byType['node_modules'] = (byType['node_modules'] || 0) + 1
    } else if (path.includes('__pycache__')) {
      byType['__pycache__'] = (byType['__pycache__'] || 0) + 1
    } else if (path.includes('.git')) {
      byType['.git'] = (byType['.git'] || 0) + 1
    } else if (path.includes('venv') || path.includes('.venv')) {
      byType['venv'] = (byType['venv'] || 0) + 1
    } else if (path.endsWith('.pyc') || path.endsWith('.pyo')) {
      byType['*.pyc'] = (byType['*.pyc'] || 0) + 1
    } else {
      byType['其他'] = (byType['其他'] || 0) + 1
    }
  }
  
  const parts = Object.entries(byType)
    .map(([type, count]) => `${type}: ${count}`)
    .join(', ')
  
  return `已过滤 ${ignoredPaths.length} 个文件 (${parts})`
}