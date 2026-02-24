import { useState } from 'react'
import './App.css'
import Backtest from './Backtest'
import StrategyBuilder from './StrategyBuilder'
import IndicatorBuilder from './IndicatorBuilder'
import KeyManager from './KeyManager'

const VIEWS = [
  { id: 'backtest',  label: 'Backtest',          icon: '▶' },
  { id: 'strategy',  label: 'Strategy Builder',  icon: '⚙' },
  { id: 'indicator', label: 'Indicator Builder', icon: '📐' },
  { id: 'keys',      label: 'Key Manager',       icon: '🔑' },
]

export default function App() {
  const [view, setView] = useState('backtest')
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
      <main className="app-content fade-up" key={view}>
        {view === 'backtest'  && <Backtest  goTo={setView} />}
        {view === 'strategy'  && <StrategyBuilder />}
        {view === 'indicator' && <IndicatorBuilder />}
        {view === 'keys'      && <KeyManager />}
      </main>
    </div>
  )
}