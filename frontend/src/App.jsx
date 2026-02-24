import { useState } from 'react'
import './App.css'
import Backtest from './Backtest'
import StrategyBuilder from './StrategyBuilder'
import IndicatorBuilder from './IndicatorBuilder'
import KeyManager from './KeyManager'

function App() {
  const [view, setView] = useState('backtest')

  return (
    <div className="container">
      <header className="header">
        <h1>Backtester Dashboard</h1>
        <nav className="nav">
          <button onClick={() => setView('backtest')}>App</button>
          <button onClick={() => setView('strategy')}>StrategyBuilder</button>
          <button onClick={() => setView('indicator')}>IndicatorBuilder</button>
          <button onClick={() => setView('keys')}>KeyManager</button>
        </nav>
      </header>

      <main>
        {view === 'backtest' && <Backtest goTo={(v) => setView(v)} />}
        {view === 'strategy' && <StrategyBuilder />}
        {view === 'indicator' && <IndicatorBuilder />}
        {view === 'keys' && <KeyManager />}
      </main>
    </div>
  )
}

export default App
