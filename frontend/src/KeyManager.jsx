import { useEffect, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

async function deriveKey(password, salt) {
  const enc = new TextEncoder();
  const baseKey = await window.crypto.subtle.importKey('raw', enc.encode(password), { name: 'PBKDF2' }, false, ['deriveKey']);
  return window.crypto.subtle.deriveKey({ name: 'PBKDF2', salt, iterations: 100000, hash: 'SHA-256' }, baseKey, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
}
async function decryptText(password, b64) {
  try {
    const raw = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const key = await deriveKey(password, raw.slice(0, 16));
    const pt = await window.crypto.subtle.decrypt({ name: 'AES-GCM', iv: raw.slice(16, 28) }, key, raw.slice(28));
    return new TextDecoder().decode(pt);
  } catch { throw new Error('Decryption failed'); }
}

const DATA_PROVIDERS = [
  { id: 'alpha-vantage', label: 'Alpha Vantage',  desc: 'Free tier available. Good for stocks & forex.', url: 'https://www.alphavantage.co/support/#api-key' },
  { id: 'polygon',       label: 'Polygon.io',      desc: 'Comprehensive market data. Free & paid plans.', url: 'https://polygon.io/dashboard/signup' },
  { id: 'yahoo-finance', label: 'Yahoo Finance',   desc: 'Free market data, good for backtesting.', url: 'https://finance.yahoo.com/' },
  { id: 'iex-cloud',     label: 'IEX Cloud',       desc: 'Real-time and historical stock data.', url: 'https://iexcloud.io/cloud-login#/register' },
  { id: 'finnhub',       label: 'Finnhub',         desc: 'Real-time data & fundamentals. Free tier.', url: 'https://finnhub.io/register' },
];

const AI_MODELS = [
  { id: 'gpt-4',            label: 'GPT-4',             provider: 'OpenAI',     desc: 'Most capable OpenAI model. Best for complex reasoning.' },
  { id: 'gpt-4o',           label: 'GPT-4o',            provider: 'OpenAI',     desc: 'Fast, multimodal. Excellent balance of speed and quality.' },
  { id: 'gpt-3.5-turbo',    label: 'GPT-3.5 Turbo',     provider: 'OpenAI',     desc: 'Fast and affordable. Good for most tasks.' },
  { id: 'claude-3-opus',    label: 'Claude 3 Opus',     provider: 'Anthropic',  desc: 'Most powerful Claude model. Great at nuanced analysis.' },
  { id: 'claude-3-sonnet',  label: 'Claude 3 Sonnet',   provider: 'Anthropic',  desc: 'Balanced performance and speed from Anthropic.' },
  { id: 'claude-3-haiku',   label: 'Claude 3 Haiku',    provider: 'Anthropic',  desc: 'Fastest and most compact Anthropic model.' },
];

const sStyle = { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, padding: '8px 12px', color: '#e5e7eb', fontSize: '0.9rem', width: '100%', outline: 'none' };
const iStyle = { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, padding: '8px 12px', color: '#e5e7eb', fontSize: '0.9rem', width: '100%', outline: 'none', fontFamily: 'ui-monospace, monospace' };

function StatusBadge({ saved }) {
  if (saved === null) return null;
  return (
    <span style={{
      fontSize: '0.72rem', fontWeight: 700, padding: '2px 10px', borderRadius: 999,
      background: saved ? 'rgba(52,211,153,0.15)' : 'rgba(239,68,68,0.1)',
      color: saved ? '#34d399' : '#f87171',
      border: `1px solid ${saved ? 'rgba(52,211,153,0.3)' : 'rgba(239,68,68,0.3)'}`,
    }}>
      {saved ? '✓ Saved' : '○ Not saved'}
    </span>
  );
}

// ─── Data Provider tab ────────────────────────────────────────────────────────
function DataProviderPanel({ initialData, onSave }) {
  const [service, setService] = useState(initialData?.service || '');
  const [apiKey, setApiKey]   = useState('');
  const [showing, setShowing] = useState(false);
  const [protect, setProtect] = useState(false);
  const [password, setPassword] = useState('');
  const [status, setStatus]   = useState(null); // null | 'saving' | 'saved' | 'error'
  const [error, setError]     = useState('');
  const [hasSaved, setHasSaved] = useState(!!initialData?.service);

  const provider = DATA_PROVIDERS.find(p => p.id === service);

  const save = async () => {
    if (!service) { setError('Choose a data provider first.'); return; }
    setError(''); setStatus('saving');
    try {
      const res = await fetch(`${API_BASE}/db/api_keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ service, dataKey: apiKey, modelKey: initialData?.modelKey ?? '', model_name: initialData?.model_name ?? '', protected: protect, password: protect ? password : undefined }),
      });
      if (!res.ok) throw new Error('Save failed');
      setStatus('saved'); setHasSaved(true);
      if (onSave) onSave({ service, hasDataKey: !!apiKey });
    } catch (e) { setStatus('error'); setError(e.message); }
  };

  const reveal = async () => {
    try {
      const res = await fetch(`${API_BASE}/db/api_keys`);
      const data = await res.json();
      const rec = data.api_key;
      if (!rec) { setError('No saved keys found'); return; }
      if (rec.protected) {
        if (!password) { setError('Enter your password to reveal'); return; }
        try {
          const dec = await fetch(`${API_BASE}/keys/decrypt`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password, dataKey: rec.data_key, modelKey: rec.model_key }) });
          const d = await dec.json();
          setApiKey(d.dataKey || '');
        } catch { setApiKey(await decryptText(password, rec.data_key)); }
      } else {
        setApiKey(atob(rec.data_key || ''));
      }
      setShowing(true);
    } catch (e) { setError(e.message); }
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: '#e5e7eb' }}>Data Provider API Key</h3>
        <StatusBadge saved={hasSaved} />
      </div>
      <p style={{ fontSize: '0.85rem', color: '#6b7280', margin: '0 0 20px' }}>
        Your data provider gives you access to historical and live price data for backtesting. You only need this if you want to fetch data directly from an API rather than uploading a CSV file.
      </p>

      <div style={{ marginBottom: 14 }}>
        <label style={{ fontSize: '0.78rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 6 }}>Choose Provider</label>
        <select value={service} style={sStyle} onChange={e => setService(e.target.value)}>
          <option value="">— Select a data provider —</option>
          {DATA_PROVIDERS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
        {provider && (
          <div style={{ marginTop: 8, display: 'flex', alignItems: 'flex-start', gap: 10, background: '#0b1120', border: '1px solid #1e293b', borderRadius: 9, padding: '10px 14px' }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '0.82rem', color: '#9ca3af' }}>{provider.desc}</div>
            </div>
            <a href={provider.url} target="_blank" rel="noopener noreferrer"
              style={{ fontSize: '0.75rem', color: '#22d3ee', textDecoration: 'none', whiteSpace: 'nowrap', padding: '3px 10px', border: '1px solid rgba(34,211,238,0.3)', borderRadius: 6 }}>
              Get API key ↗
            </a>
          </div>
        )}
      </div>

      <div style={{ marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <label style={{ fontSize: '0.78rem', fontWeight: 700, color: '#9ca3af' }}>API Key</label>
          {hasSaved && !showing && (
            <button style={{ fontSize: '0.72rem', background: 'transparent', border: '1px solid #334155', borderRadius: 6, color: '#9ca3af', cursor: 'pointer', padding: '2px 8px' }}
              onClick={reveal}>Reveal saved key</button>
          )}
          {showing && (
            <button style={{ fontSize: '0.72rem', background: 'transparent', border: '1px solid #334155', borderRadius: 6, color: '#9ca3af', cursor: 'pointer', padding: '2px 8px' }}
              onClick={() => { setApiKey(''); setShowing(false); }}>Hide</button>
          )}
        </div>
        <input type={showing ? 'text' : 'password'} value={apiKey} onChange={e => setApiKey(e.target.value)}
          style={iStyle} placeholder={hasSaved ? '••••••••••••• (saved)' : 'Paste your API key here'} />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: protect ? 12 : 20 }}>
        <input type="checkbox" id="dp-protect" checked={protect} onChange={e => setProtect(e.target.checked)} style={{ cursor: 'pointer' }} />
        <label htmlFor="dp-protect" style={{ fontSize: '0.85rem', color: '#9ca3af', cursor: 'pointer' }}>
          🔒 Encrypt key with a password
        </label>
      </div>

      {protect && (
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: '0.78rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 6 }}>Password</label>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)}
            style={iStyle} placeholder="Choose a password to encrypt your key" />
          <p style={{ fontSize: '0.75rem', color: '#6b7280', margin: '6px 0 0' }}>You'll need this password to reveal your key later. Don't lose it!</p>
        </div>
      )}

      {error && <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, padding: '8px 14px', color: '#fca5a5', fontSize: '0.84rem', marginBottom: 12 }}>{error}</div>}

      <button style={{ background: status === 'saving' ? '#1e293b' : 'linear-gradient(135deg,#6366f1,#22d3ee)', border: 'none', borderRadius: 999, padding: '9px 22px', color: '#0f172a', fontWeight: 700, cursor: 'pointer', fontSize: '0.9rem', opacity: status === 'saving' ? 0.7 : 1 }}
        onClick={save} disabled={status === 'saving'}>
        {status === 'saving' ? 'Saving…' : 'Save API Key'}
      </button>
    </div>
  );
}

// ─── AI Model tab ─────────────────────────────────────────────────────────────
function AIModelPanel({ initialData }) {
  const [modelName, setModelName] = useState(initialData?.model_name || '');
  const [modelKey, setModelKey]   = useState('');
  const [showing, setShowing]     = useState(false);
  const [protect, setProtect]     = useState(false);
  const [password, setPassword]   = useState('');
  const [status, setStatus]       = useState(null);
  const [error, setError]         = useState('');
  const [hasSaved, setHasSaved]   = useState(!!initialData?.model_name);

  const selectedModel = AI_MODELS.find(m => m.id === modelName);

  // Group by provider
  const byProvider = AI_MODELS.reduce((acc, m) => {
    (acc[m.provider] = acc[m.provider] || []).push(m);
    return acc;
  }, {});

  const save = async () => {
    if (!modelName) { setError('Choose an AI model first.'); return; }
    setError(''); setStatus('saving');
    try {
      const res = await fetch(`${API_BASE}/db/api_keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ service: initialData?.service ?? '', dataKey: initialData?.dataKey ?? '', model_name: modelName, modelKey, protected: protect, password: protect ? password : undefined }),
      });
      if (!res.ok) throw new Error('Save failed');
      setStatus('saved'); setHasSaved(true);
    } catch (e) { setStatus('error'); setError(e.message); }
  };

  const reveal = async () => {
    try {
      const res = await fetch(`${API_BASE}/db/api_keys`);
      const data = await res.json();
      const rec = data.api_key;
      if (!rec) { setError('No saved keys found'); return; }
      if (rec.protected) {
        if (!password) { setError('Enter your password to reveal'); return; }
        try {
          const dec = await fetch(`${API_BASE}/keys/decrypt`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password, dataKey: rec.data_key, modelKey: rec.model_key }) });
          const d = await dec.json();
          setModelKey(d.modelKey || '');
        } catch { setModelKey(await decryptText(password, rec.model_key)); }
      } else {
        setModelKey(atob(rec.model_key || ''));
      }
      setShowing(true);
    } catch (e) { setError(e.message); }
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 20 }}>
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: '#e5e7eb' }}>AI Model API Key</h3>
        <StatusBadge saved={hasSaved} />
      </div>
      <p style={{ fontSize: '0.85rem', color: '#6b7280', margin: '0 0 20px' }}>
        An AI model key is only needed if you use AI-powered features in this app. It's completely separate from your data provider — you can use one without the other.
      </p>

      <div style={{ marginBottom: 14 }}>
        <label style={{ fontSize: '0.78rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 6 }}>Choose AI Model</label>
        <select value={modelName} style={sStyle} onChange={e => setModelName(e.target.value)}>
          <option value="">— Select an AI model —</option>
          {Object.entries(byProvider).map(([provider, models]) => (
            <optgroup key={provider} label={provider}>
              {models.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
            </optgroup>
          ))}
        </select>
        {selectedModel && (
          <div style={{ marginTop: 8, background: '#0b1120', border: '1px solid #1e293b', borderRadius: 9, padding: '10px 14px' }}>
            <div style={{ fontSize: '0.72rem', fontWeight: 700, color: '#6b7280', marginBottom: 2 }}>{selectedModel.provider}</div>
            <div style={{ fontSize: '0.82rem', color: '#9ca3af' }}>{selectedModel.desc}</div>
          </div>
        )}
      </div>

      <div style={{ marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <label style={{ fontSize: '0.78rem', fontWeight: 700, color: '#9ca3af' }}>API Key</label>
          {hasSaved && !showing && (
            <button style={{ fontSize: '0.72rem', background: 'transparent', border: '1px solid #334155', borderRadius: 6, color: '#9ca3af', cursor: 'pointer', padding: '2px 8px' }}
              onClick={reveal}>Reveal saved key</button>
          )}
          {showing && (
            <button style={{ fontSize: '0.72rem', background: 'transparent', border: '1px solid #334155', borderRadius: 6, color: '#9ca3af', cursor: 'pointer', padding: '2px 8px' }}
              onClick={() => { setModelKey(''); setShowing(false); }}>Hide</button>
          )}
        </div>
        <input type={showing ? 'text' : 'password'} value={modelKey} onChange={e => setModelKey(e.target.value)}
          style={iStyle} placeholder={hasSaved ? '••••••••••••• (saved)' : 'Paste your API key here'} />
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: protect ? 12 : 20 }}>
        <input type="checkbox" id="ai-protect" checked={protect} onChange={e => setProtect(e.target.checked)} style={{ cursor: 'pointer' }} />
        <label htmlFor="ai-protect" style={{ fontSize: '0.85rem', color: '#9ca3af', cursor: 'pointer' }}>
          🔒 Encrypt key with a password
        </label>
      </div>

      {protect && (
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: '0.78rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 6 }}>Password</label>
          <input type="password" value={password} onChange={e => setPassword(e.target.value)}
            style={iStyle} placeholder="Choose a password to encrypt your key" />
          <p style={{ fontSize: '0.75rem', color: '#6b7280', margin: '6px 0 0' }}>You'll need this password to reveal your key later.</p>
        </div>
      )}

      {error && <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 8, padding: '8px 14px', color: '#fca5a5', fontSize: '0.84rem', marginBottom: 12 }}>{error}</div>}

      <button style={{ background: status === 'saving' ? '#1e293b' : 'linear-gradient(135deg,#a78bfa,#22d3ee)', border: 'none', borderRadius: 999, padding: '9px 22px', color: '#0f172a', fontWeight: 700, cursor: 'pointer', fontSize: '0.9rem', opacity: status === 'saving' ? 0.7 : 1 }}
        onClick={save} disabled={status === 'saving'}>
        {status === 'saving' ? 'Saving…' : 'Save Model Key'}
      </button>
    </div>
  );
}

// ─── Main ─────────────────────────────────────────────────────────────────────
export default function KeyManager() {
  const [tab, setTab]         = useState('data');
  const [savedData, setSaved] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/db/api_keys`)
      .then(r => r.json())
      .then(d => { if (d.api_key) setSaved(d.api_key); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const tabs = [
    { id: 'data',  label: '📡 Data Provider', desc: 'for fetching market data' },
    { id: 'ai',    label: '🤖 AI Model',       desc: 'for AI-powered features' },
  ];

  return (
    <div className="view">
      <h2>Key Manager</h2>
      <p>Manage your API keys. Your data provider key and AI model key are independent — you can use either or both.</p>

      <div style={{ display: 'flex', gap: 10, margin: '1.5rem 0 1.5rem', background: '#0f172a', padding: 6, borderRadius: 14, border: '1px solid #1f2937', width: 'fit-content' }}>
        {tabs.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            style={{
              background: tab === t.id ? '#1e293b' : 'transparent',
              border: tab === t.id ? '1px solid #334155' : '1px solid transparent',
              borderRadius: 10, padding: '8px 18px', cursor: 'pointer',
              color: tab === t.id ? '#e5e7eb' : '#6b7280', fontSize: '0.87rem', fontWeight: tab === t.id ? 700 : 400,
              transition: 'all 0.2s',
            }}>
            {t.label}
            <div style={{ fontSize: '0.67rem', color: tab === t.id ? '#9ca3af' : '#4b5563', fontWeight: 400 }}>{t.desc}</div>
          </button>
        ))}
      </div>

      {loading ? (
        <div style={{ color: '#6b7280', padding: 40, textAlign: 'center' }}>Loading…</div>
      ) : (
        <div style={{ background: '#111827', border: '1px solid #1f2937', borderRadius: 16, padding: '1.5rem', maxWidth: 560 }}>
          {tab === 'data' && <DataProviderPanel initialData={savedData} onSave={d => setSaved(prev => ({ ...prev, ...d }))} />}
          {tab === 'ai'   && <AIModelPanel initialData={savedData} />}
        </div>
      )}
    </div>
  );
}