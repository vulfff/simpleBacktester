import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import './App.css'
import Backtest from './Backtest'
import StrategyBuilder from './StrategyBuilder'
import IndicatorBuilder from './IndicatorBuilder'
import KeyManager from './KeyManager'
import Analytics from './Analytics'
import Analyzer from './Analyzer'

function UpdateBanner() {
  const [info, setInfo] = useState(null)
  const [dismissed, setDismissed] = useState(false)

  useEffect(() => {
    fetch('/api/version').then(r => r.json()).then(setInfo).catch(() => {})
  }, [])

  if (!info || !info.latest || dismissed) return null
  if (info.latest === info.current) return null

  return (
    <div className="alert alert-warn" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <span>
        Update available: <strong>{info.latest}</strong> (you are on {info.current}).{' '}
        {info.url && <a href={info.url} target="_blank" rel="noreferrer">Download</a>}
      </span>
      <button className="btn btn-sm" onClick={() => setDismissed(true)}>Dismiss</button>
    </div>
  )
}

const VIEW_IDS = [
  { id: 'backtest',  tKey: 'nav.backtest',  icon: '▶' },
  { id: 'analytics', tKey: 'nav.analytics', icon: '📈' },
  { id: 'strategy',  tKey: 'nav.strategy',  icon: '⚙' },
  { id: 'indicator', tKey: 'nav.indicator', icon: '📐' },
  { id: 'analyzer',  tKey: 'nav.analyzer',  icon: '🔍' },
  { id: 'keys',      tKey: 'nav.keys',      icon: '🔑' },
]

const LANGS = ['en', 'et']

export default function App() {
  const [view, setView] = useState('backtest')
  const [appVersion, setAppVersion] = useState(null)
  const { t, i18n } = useTranslation()
  const isWide = view === 'analytics'

  useEffect(() => {
    fetch('/api/version').then(r => r.json()).then(d => setAppVersion(d.current)).catch(() => {})
  }, [])

  function switchLang(lng) {
    i18n.changeLanguage(lng)
  }

  return (
    <div className="app-shell">
      <UpdateBanner />
      <header className="app-topbar">
        <div className="app-logo">
          <div className="app-logo-mark">📊</div>
          <span className="app-logo-text">{t('app.title')}</span>
          {appVersion && <span style={{ fontSize: '0.7rem', color: 'var(--fg, #888)', opacity: 0.5, marginLeft: 4 }}>v{appVersion}</span>}
        </div>
        <nav className="app-nav">
          {VIEW_IDS.map(v => (
            <button key={v.id}
              className={`nav-btn${view === v.id ? ' active' : ''}`}
              onClick={() => setView(v.id)}>
              <span style={{fontSize:'0.85rem'}}>{v.icon}</span>{t(v.tKey)}
            </button>
          ))}
        </nav>
        <div style={{ display: 'flex', gap: '4px', marginLeft: '12px', flexShrink: 0 }}>
          {LANGS.map(lng => (
            <button
              key={lng}
              onClick={() => switchLang(lng)}
              style={{
                padding: '3px 10px',
                borderRadius: '999px',
                border: '1px solid var(--border)',
                background: i18n.language === lng ? 'var(--accent)' : 'transparent',
                color: i18n.language === lng ? '#fff' : 'var(--fg, #ccc)',
                cursor: 'pointer',
                fontSize: '0.75rem',
                fontWeight: 600,
                lineHeight: 1.4,
              }}
            >
              {t(`lang.${lng}`)}
            </button>
          ))}
        </div>
      </header>
      <main className="app-content fade-up" key={view} style={isWide ? { maxWidth: '1440px' } : {}}>
        {view === 'backtest'   && <Backtest   goTo={setView} />}
        {view === 'analytics'  && <Analytics  goTo={setView} />}
        {view === 'strategy'   && <StrategyBuilder />}
        {view === 'indicator'  && <IndicatorBuilder />}
        {view === 'analyzer'   && <Analyzer />}
        {view === 'keys'       && <KeyManager />}
      </main>
    </div>
  )
}
