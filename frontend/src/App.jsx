import { useState } from 'react'
import './App.css'
import Backtest from './Backtest'
import StrategyBuilder from './StrategyBuilder'
import IndicatorBuilder from './IndicatorBuilder'
import KeyManager from './KeyManager'
import Analytics from './Analytics'

const VIEWS = [
  { id: 'backtest',   label: 'Backtest',          icon: '▶' },
  { id: 'analytics',  label: 'Analytics',          icon: '📈' },
  { id: 'strategy',   label: 'Strategy Builder',  icon: '⚙' },
  { id: 'indicator',  label: 'Indicator Builder', icon: '📐' },
  { id: 'keys',       label: 'Key Manager',       icon: '🔑' },
]

export default function App() {
  const [view, setView] = useState('backtest')
  // Analytics page needs wider content area
  const isWide = view === 'analytics'
  return (
    <div className="app-shell">
      <header className="app-topbar">
        <div className="app-logo">
          <div className="app-logo-mark">📊</div>
          <span className="app-logo-text">Backtester</span>
        </div>
        <nav className="app-nav">
          {VIEWS.map(v => (
            <button key={v.id}
              className={`nav-btn${view === v.id ? ' active' : ''}`}
              onClick={() => setView(v.id)}>
              <span style={{fontSize:'0.85rem'}}>{v.icon}</span>{v.label}
            </button>
          ))}
        </nav>
      </header>
      <main className="app-content fade-up" key={view} style={isWide ? { maxWidth: '1440px' } : {}}>
        {view === 'backtest'   && <Backtest   goTo={setView} />}
        {view === 'analytics'  && <Analytics  goTo={setView} />}
        {view === 'strategy'   && <StrategyBuilder />}
        {view === 'indicator'  && <IndicatorBuilder />}
        {view === 'keys'       && <KeyManager />}
      </main>
    </div>
  )
}