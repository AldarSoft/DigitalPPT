import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AppRouter } from './router'
import { AppProviders } from './providers'

export default function App() {
  return (
    <AppErrorBoundary>
      <AppProviders>
        <AppRouter />
      </AppProviders>
    </AppErrorBoundary>
  )
}

class AppErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Application render failed', error, info)
  }

  render() {
    if (this.state.failed) {
      return <main className="flex min-h-screen items-center justify-center bg-surface px-5"><section className="w-full max-w-md rounded-panel border border-border bg-white p-6 text-center"><h1 className="text-2xl">The page could not be displayed</h1><p className="mt-3 text-sm text-muted">Reload the page to restore the current session.</p><button className="mt-5 min-h-11 rounded-control border-0 bg-brand px-5 text-sm font-bold text-white" type="button" onClick={() => window.location.reload()}>Reload page</button></section></main>
    }
    return this.props.children
  }
}
