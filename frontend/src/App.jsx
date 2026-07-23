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
  { id: 'backtest',  tKey: 'nav.backtest' },
  { id: 'analytics', tKey: 'nav.analytics' },
  { id: 'strategy',  tKey: 'nav.strategy' },
  { id: 'indicator', tKey: 'nav.indicator' },
  { id: 'analyzer',  tKey: 'nav.analyzer' },
  { id: 'keys',      tKey: 'nav.keys' },
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
          <div className="app-logo-mark">❚❚</div>
          <span className="app-logo-text">{t('app.title')}</span>
          {appVersion && <span style={{ fontFamily: 'var(--mono)', fontSize: '0.66rem', color: 'var(--text-mute)', marginLeft: 4 }}>v{appVersion}</span>}
        </div>
        <nav className="app-nav">
          {VIEW_IDS.map(v => (
            <button key={v.id}
              className={`nav-btn${view === v.id ? ' active' : ''}`}
              onClick={() => setView(v.id)}>
              {t(v.tKey)}
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
                borderRadius: 'var(--r-sm)',
                border: '1px solid var(--border)',
                background: i18n.language === lng ? 'var(--accent)' : 'transparent',
                color: i18n.language === lng ? '#1a1206' : 'var(--text-mute)',
                cursor: 'pointer',
                fontFamily: 'var(--disp)',
                fontSize: '0.7rem',
                fontWeight: 600,
                letterSpacing: '0.08em',
                textTransform: 'uppercase',
                lineHeight: 1.5,
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
