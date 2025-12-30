import { ReactNode } from 'react'

interface LayoutProps {
  children: ReactNode
}

// Simple pass-through layout - each page handles its own layout
export default function Layout({ children }: LayoutProps) {
  return <>{children}</>
}