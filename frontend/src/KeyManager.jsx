import { useEffect, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

// ── Provider / model metadata ─────────────────────────────────────────────────

const DATA_PROVIDERS = [
  { id: 'massive',       label: 'Massive',        assets: 'Stocks · Crypto · Forex · Options', rateLimits: '5 req/min free · Unlimited paid', tier: 'Free + Paid', keyHint: 'Alphanumeric key from dashboard', url: 'https://massive.com/dashboard', desc: 'Comprehensive market data. Free key on sign-up — no credit card.' },
  { id: 'alpha-vantage', label: 'Alpha Vantage',  assets: 'Stocks · Forex · Crypto',           rateLimits: '25 req/day free · 500+/min paid',  tier: 'Free + Paid', keyHint: 'Alphanumeric key',                url: 'https://www.alphavantage.co/support/#api-key', desc: 'Solid free tier for US stocks, forex and crypto.' },
  { id: 'polygon',       label: 'Polygon.io',     assets: 'Stocks · Options · Crypto · Forex', rateLimits: '5 req/min free · Unlimited paid',  tier: 'Free + Paid', keyHint: 'Alphanumeric key',                url: 'https://polygon.io/dashboard/signup', desc: 'Deep US market data. Rebranded to Massive (see above).' },
  { id: 'yahoo-finance', label: 'Yahoo Finance',  assets: 'Stocks · ETFs · Crypto',            rateLimits: 'Unofficial API — may throttle',    tier: 'Free (no key)', keyHint: 'No key needed — leave blank',  url: null, desc: 'No API key required. Good for quick backtests.' },
  { id: 'finnhub',       label: 'Finnhub',        assets: 'Stocks · Forex · Crypto',           rateLimits: '60 req/min free',                  tier: 'Free + Paid', keyHint: 'Alphanumeric key from dashboard', url: 'https://finnhub.io/register', desc: 'Real-time & historical data plus fundamentals.' },
  { id: 'iex-cloud',     label: 'IEX Cloud',      assets: 'Stocks · ETFs',                     rateLimits: '500K messages/mo free',            tier: 'Free + Paid', keyHint: 'Starts with pk_ or sk_',          url: 'https://iexcloud.io/cloud-login#/register', desc: 'High-quality US equity data.' },
];

const AI_MODELS = [
  // Anthropic
  { id: 'claude-opus-4-6',            label: 'Claude Opus 4.6',      provider: 'anthropic', providerLabel: 'Anthropic', desc: 'Most capable Anthropic model. Best for complex reasoning.',            keyHint: 'Starts with sk-ant-', url: 'https://console.anthropic.com/' },
  { id: 'claude-sonnet-4-6',          label: 'Claude Sonnet 4.6',    provider: 'anthropic', providerLabel: 'Anthropic', desc: 'Latest Sonnet. Excellent speed and capability balance.',               keyHint: 'Starts with sk-ant-', url: 'https://console.anthropic.com/' },
  { id: 'claude-3-5-sonnet-20241022', label: 'Claude 3.5 Sonnet',    provider: 'anthropic', providerLabel: 'Anthropic', desc: 'Highly capable. Great for complex strategy generation tasks.',         keyHint: 'Starts with sk-ant-', url: 'https://console.anthropic.com/' },
  { id: 'claude-3-5-haiku-20241022',  label: 'Claude 3.5 Haiku',     provider: 'anthropic', providerLabel: 'Anthropic', desc: 'Fast and affordable Anthropic model.',                               keyHint: 'Starts with sk-ant-', url: 'https://console.anthropic.com/' },
  // OpenAI
  { id: 'gpt-4.1',                    label: 'GPT-4.1',              provider: 'openai',    providerLabel: 'OpenAI',    desc: 'Flagship GPT-4.1. Best OpenAI reasoning and instruction following.',  keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  { id: 'gpt-4.1-mini',               label: 'GPT-4.1 Mini',         provider: 'openai',    providerLabel: 'OpenAI',    desc: 'Fast and affordable GPT-4.1 variant.',                               keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  { id: 'gpt-4o',                     label: 'GPT-4o',               provider: 'openai',    providerLabel: 'OpenAI',    desc: 'Fast multimodal flagship. Excellent speed + capability balance.',     keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  { id: 'gpt-4o-mini',                label: 'GPT-4o Mini',          provider: 'openai',    providerLabel: 'OpenAI',    desc: 'Affordable and fast. Good for most strategy tasks.',                  keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  { id: 'o3',                         label: 'o3',                   provider: 'openai',    providerLabel: 'OpenAI',    desc: 'OpenAI o3 reasoning model. Strongest for complex analysis.',          keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  { id: 'o4-mini',                    label: 'o4-mini',              provider: 'openai',    providerLabel: 'OpenAI',    desc: 'Efficient o4 reasoning model.',                                       keyHint: 'Starts with sk-',     url: 'https://platform.openai.com/api-keys' },
  // xAI
  { id: 'grok-3',                     label: 'Grok-3',               provider: 'grok',      providerLabel: 'xAI',       desc: 'Latest xAI flagship model.',                                         keyHint: 'Starts with xai-',    url: 'https://console.x.ai' },
  { id: 'grok-3-mini',                label: 'Grok-3 Mini',          provider: 'grok',      providerLabel: 'xAI',       desc: 'Fast and efficient Grok-3 variant.',                                  keyHint: 'Starts with xai-',    url: 'https://console.x.ai' },
  { id: 'grok-2',                     label: 'Grok-2',               provider: 'grok',      providerLabel: 'xAI',       desc: 'Stable xAI model with strong reasoning.',                            keyHint: 'Starts with xai-',    url: 'https://console.x.ai' },
  // Google
  { id: 'gemini-2.5-pro',             label: 'Gemini 2.5 Pro',       provider: 'gemini',    providerLabel: 'Google',    desc: 'Most capable Gemini model. Best for complex tasks.',                  keyHint: 'Starts with AIza',    url: 'https://aistudio.google.com/app/apikey' },
  { id: 'gemini-2.5-flash',           label: 'Gemini 2.5 Flash',     provider: 'gemini',    providerLabel: 'Google',    desc: 'Fast Gemini 2.5 variant. Good speed/quality tradeoff.',               keyHint: 'Starts with AIza',    url: 'https://aistudio.google.com/app/apikey' },
  { id: 'gemini-2.0-flash',           label: 'Gemini 2.0 Flash',     provider: 'gemini',    providerLabel: 'Google',    desc: 'Proven fast Gemini model. Strong performance.',                       keyHint: 'Starts with AIza',    url: 'https://aistudio.google.com/app/apikey' },
];

const PROVIDER_COLORS = { anthropic: '#f59e0b', openai: '#10b981', grok: '#8b5cf6', gemini: '#3b82f6' };

/** Infer AI provider from API key prefix. Returns null if unrecognised. */
function inferProviderFromKey(key) {
  const k = key.trim();
  if (k.startsWith('sk-ant-'))  return 'anthropic'; // must precede 'sk-' check
  if (k.startsWith('xai-'))     return 'grok';
  if (k.startsWith('AIza'))     return 'gemini';
  if (k.startsWith('sk-'))      return 'openai';
  return null;
}

const sStyle = { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, padding: '8px 12px', color: '#e5e7eb', fontSize: '0.88rem', width: '100%', outline: 'none' };
const iStyle = { background: '#0f172a', border: '1px solid #334155', borderRadius: 8, padding: '8px 12px', color: '#e5e7eb', fontSize: '0.88rem', width: '100%', outline: 'none', fontFamily: 'ui-monospace, monospace' };

// ── Shared sub-components ─────────────────────────────────────────────────────

function ActiveDot({ active }) {
  return (
    <span style={{
      width: 8, height: 8, borderRadius: '50%', flexShrink: 0, marginTop: 1,
      background: active ? '#34d399' : '#334155',
      boxShadow: active ? '0 0 6px rgba(52,211,153,0.6)' : 'none',
    }} />
  );
}

function KeyRow({ label, sublabel, active, onActivate, onDelete }) {
  const [confirmDel, setConfirmDel] = useState(false);
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
      background: active ? 'rgba(52,211,153,0.05)' : '#0b1120',
      border: `1px solid ${active ? 'rgba(52,211,153,0.25)' : '#1e293b'}`,
      borderRadius: 8, marginBottom: 6,
    }}>
      <ActiveDot active={active} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: '0.87rem', fontWeight: 600, color: active ? '#e2e8f0' : '#94a3b8' }}>{label}</div>
        {sublabel && <div style={{ fontSize: '0.72rem', color: '#4b5563', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{sublabel}</div>}
      </div>
      {active ? (
        <span style={{ fontSize: '0.68rem', fontWeight: 700, padding: '2px 8px', borderRadius: 999,
          background: 'rgba(52,211,153,0.12)', border: '1px solid rgba(52,211,153,0.3)', color: '#34d399' }}>
          Active
        </span>
      ) : (
        <button onClick={onActivate}
          style={{ fontSize: '0.75rem', background: 'rgba(59,130,246,0.1)', border: '1px solid rgba(59,130,246,0.3)',
            borderRadius: 6, color: '#93c5fd', cursor: 'pointer', padding: '3px 10px', whiteSpace: 'nowrap' }}>
          Use this
        </button>
      )}
      {confirmDel ? (
        <>
          <button onClick={onDelete}
            style={{ fontSize: '0.72rem', background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.4)',
              borderRadius: 6, color: '#f87171', cursor: 'pointer', padding: '3px 8px' }}>Confirm</button>
          <button onClick={() => setConfirmDel(false)}
            style={{ fontSize: '0.72rem', background: 'transparent', border: '1px solid #334155',
              borderRadius: 6, color: '#6b7280', cursor: 'pointer', padding: '3px 8px' }}>Cancel</button>
        </>
      ) : (
        <button onClick={() => setConfirmDel(true)}
          style={{ fontSize: '0.72rem', background: 'transparent', border: '1px solid #1e293b',
            borderRadius: 6, color: '#4b5563', cursor: 'pointer', padding: '3px 8px', lineHeight: 1 }}>×</button>
      )}
    </div>
  );
}

// ── Data Provider panel ───────────────────────────────────────────────────────

function DataProviderPanel() {
  const [keys, setKeys]         = useState([]);
  const [loading, setLoading]   = useState(true);
  const [service, setService]   = useState('');
  const [apiKey, setApiKey]     = useState('');
  const [label, setLabel]       = useState('');
  const [protect, setProtect]   = useState(false);
  const [password, setPassword] = useState('');
  const [saving, setSaving]     = useState(false);
  const [error, setError]       = useState('');

  const load = () => {
    setLoading(true);
    fetch(`${API_BASE}/db/data-keys`)
      .then(r => r.json())
      .then(d => setKeys(d.keys || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const provider = DATA_PROVIDERS.find(p => p.id === service);

  const save = async () => {
    if (!service) { setError('Choose a provider first.'); return; }
    if (service !== 'yahoo-finance' && !apiKey) { setError('Paste your API key.'); return; }
    setError(''); setSaving(true);
    try {
      const r = await fetch(`${API_BASE}/db/data-keys`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ service, key: apiKey, protected: protect, password: protect ? password : undefined, label, activate: true }),
      });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || 'Save failed'); }
      setApiKey(''); setLabel(''); setService(''); setProtect(false); setPassword('');
      load();
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  const activate = async id => {
    await fetch(`${API_BASE}/db/data-keys/${id}/activate`, { method: 'POST' });
    load();
  };

  const remove = async id => {
    await fetch(`${API_BASE}/db/data-keys/${id}`, { method: 'DELETE' });
    load();
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: '#e5e7eb' }}>Data Providers</h3>
        <span style={{ fontSize: '0.72rem', color: '#4b5563' }}>{keys.length} saved</span>
      </div>
      <p style={{ fontSize: '0.83rem', color: '#6b7280', margin: '0 0 16px' }}>
        Store multiple data provider keys and switch the active one anytime. Only the active provider is used for API fetches.
      </p>

      {/* Saved key list */}
      {loading ? (
        <div style={{ color: '#4b5563', fontSize: '0.83rem', padding: '12px 0' }}>Loading…</div>
      ) : keys.length === 0 ? (
        <div style={{ color: '#4b5563', fontSize: '0.83rem', padding: '10px 14px', background: '#0b1120', borderRadius: 8, marginBottom: 16, border: '1px dashed #1e293b' }}>
          No data keys saved yet. Add one below.
        </div>
      ) : (
        <div style={{ marginBottom: 16 }}>
          {keys.map(k => {
            const meta = DATA_PROVIDERS.find(p => p.id === k.service);
            return (
              <KeyRow key={k.id}
                label={meta?.label || k.service}
                sublabel={k.label || meta?.assets}
                active={!!k.active}
                onActivate={() => activate(k.id)}
                onDelete={() => remove(k.id)} />
            );
          })}
        </div>
      )}

      {/* Add new key form */}
      <div style={{ background: '#0b1120', border: '1px solid #1e293b', borderRadius: 10, padding: '14px' }}>
        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#6b7280', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Add New</div>

        <div style={{ marginBottom: 10 }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 5 }}>Provider</label>
          <select value={service} style={sStyle} onChange={e => setService(e.target.value)}>
            <option value="">— Select provider —</option>
            {DATA_PROVIDERS.map(p => <option key={p.id} value={p.id}>{p.label}</option>)}
          </select>
          {provider && (
            <div style={{ marginTop: 6, fontSize: '0.75rem', color: '#6b7280', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
              <span>📊 {provider.assets}</span>
              <span>⚡ {provider.rateLimits}</span>
              {provider.url && (
                <a href={provider.url} target="_blank" rel="noopener noreferrer"
                  style={{ color: '#22d3ee', textDecoration: 'none' }}>Get key ↗</a>
              )}
            </div>
          )}
        </div>

        {service !== 'yahoo-finance' && (
          <div style={{ marginBottom: 10 }}>
            <label style={{ fontSize: '0.75rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 5 }}>API Key</label>
            <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)}
              style={iStyle} placeholder={provider?.keyHint || 'Paste API key here'} autoComplete="off" />
          </div>
        )}

        <div style={{ marginBottom: 10 }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 5 }}>Label <span style={{ fontWeight: 400, color: '#4b5563' }}>(optional)</span></label>
          <input value={label} onChange={e => setLabel(e.target.value)}
            style={sStyle} placeholder="e.g. Personal, Work" />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: protect ? 10 : 14 }}>
          <input type="checkbox" id="dp-protect" checked={protect} onChange={e => setProtect(e.target.checked)} style={{ cursor: 'pointer' }} />
          <label htmlFor="dp-protect" style={{ fontSize: '0.83rem', color: '#9ca3af', cursor: 'pointer' }}>🔒 Encrypt with password</label>
        </div>
        {protect && (
          <div style={{ marginBottom: 14 }}>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              style={iStyle} placeholder="Choose a password" />
          </div>
        )}

        {error && <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 7, padding: '7px 12px', color: '#fca5a5', fontSize: '0.82rem', marginBottom: 10 }}>{error}</div>}

        <button onClick={save} disabled={saving}
          style={{ background: saving ? '#1e293b' : 'linear-gradient(135deg,#6366f1,#22d3ee)', border: 'none', borderRadius: 999, padding: '8px 20px', color: '#0f172a', fontWeight: 700, cursor: saving ? 'not-allowed' : 'pointer', fontSize: '0.87rem', opacity: saving ? 0.7 : 1 }}>
          {saving ? 'Saving…' : 'Save & Activate'}
        </button>
      </div>
    </div>
  );
}

// ── AI Model panel ────────────────────────────────────────────────────────────

function AIModelPanel() {
  const [keys, setKeys]         = useState([]);
  const [loading, setLoading]   = useState(true);
  const [modelName, setModelName] = useState('');
  const [apiKey, setApiKey]     = useState('');
  const [label, setLabel]       = useState('');
  const [protect, setProtect]   = useState(false);
  const [password, setPassword] = useState('');
  const [saving, setSaving]           = useState(false);
  const [error, setError]             = useState('');
  const [detectedProvider, setDetectedProvider] = useState(null);
  const [fetchedModels, setFetchedModels]       = useState([]);
  const [fetching, setFetching]                 = useState(false);
  const [fetchError, setFetchError]             = useState('');

  const load = () => {
    setLoading(true);
    fetch(`${API_BASE}/db/model-keys`)
      .then(r => r.json())
      .then(d => setKeys(d.keys || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(load, []);

  const selectedModel = AI_MODELS.find(m => m.id === modelName);

  // Group models by provider for <optgroup>
  const byProvider = AI_MODELS.reduce((acc, m) => {
    (acc[m.providerLabel] = acc[m.providerLabel] || []).push(m);
    return acc;
  }, {});

  const save = async () => {
    if (!modelName) { setError('Choose a model first.'); return; }
    if (!apiKey) { setError('Paste your API key.'); return; }
    setError(''); setSaving(true);
    const knownModel = AI_MODELS.find(m => m.id === modelName);
    const providerToSave = knownModel?.provider || detectedProvider || '';
    try {
      const r = await fetch(`${API_BASE}/db/model-keys`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: modelName, provider: providerToSave, key: apiKey, protected: protect, password: protect ? password : undefined, label, activate: true }),
      });
      if (!r.ok) { const d = await r.json(); throw new Error(d.detail || 'Save failed'); }
      setApiKey(''); setLabel(''); setModelName(''); setProtect(false); setPassword('');
      setDetectedProvider(null); setFetchedModels([]); setFetchError('');
      load();
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  const activate = async id => {
    await fetch(`${API_BASE}/db/model-keys/${id}/activate`, { method: 'POST' });
    load();
  };

  const remove = async id => {
    await fetch(`${API_BASE}/db/model-keys/${id}`, { method: 'DELETE' });
    load();
  };

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700, color: '#e5e7eb' }}>AI Models</h3>
        <span style={{ fontSize: '0.72rem', color: '#4b5563' }}>{keys.length} saved</span>
      </div>
      <p style={{ fontSize: '0.83rem', color: '#6b7280', margin: '0 0 16px' }}>
        Store keys for multiple AI providers and switch between them. Only the active model is used for AI features.
      </p>

      {/* Saved key list */}
      {loading ? (
        <div style={{ color: '#4b5563', fontSize: '0.83rem', padding: '12px 0' }}>Loading…</div>
      ) : keys.length === 0 ? (
        <div style={{ color: '#4b5563', fontSize: '0.83rem', padding: '10px 14px', background: '#0b1120', borderRadius: 8, marginBottom: 16, border: '1px dashed #1e293b' }}>
          No AI model keys saved yet. Add one below.
        </div>
      ) : (
        <div style={{ marginBottom: 16 }}>
          {keys.map(k => {
            const meta = AI_MODELS.find(m => m.id === k.model_name);
            const provColor = PROVIDER_COLORS[k.provider] || '#6b7280';
            return (
              <KeyRow key={k.id}
                label={meta?.label || k.model_name}
                sublabel={
                  <span>
                    {k.label ? <>{k.label} · </> : null}
                    <span style={{ color: provColor }}>{meta?.providerLabel || k.provider}</span>
                  </span>
                }
                active={!!k.active}
                onActivate={() => activate(k.id)}
                onDelete={() => remove(k.id)} />
            );
          })}
        </div>
      )}

      {/* Add new key form */}
      <div style={{ background: '#0b1120', border: '1px solid #1e293b', borderRadius: 10, padding: '14px' }}>
        <div style={{ fontSize: '0.78rem', fontWeight: 700, color: '#6b7280', marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Add New</div>

        <div style={{ marginBottom: 10 }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 5 }}>Model</label>
          <select value={modelName} style={sStyle} onChange={e => setModelName(e.target.value)}>
            <option value="">— Select model —</option>
            {Object.entries(byProvider).map(([prov, models]) => (
              <optgroup key={prov} label={prov}>
                {models.map(m => <option key={m.id} value={m.id}>{m.label}</option>)}
              </optgroup>
            ))}
          </select>
          {selectedModel && (
            <div style={{ marginTop: 6, fontSize: '0.75rem', color: '#6b7280', display: 'flex', gap: 10, alignItems: 'center' }}>
              <span style={{ color: PROVIDER_COLORS[selectedModel.provider] || '#6b7280', fontWeight: 600 }}>{selectedModel.providerLabel}</span>
              <span>{selectedModel.desc}</span>
              <a href={selectedModel.url} target="_blank" rel="noopener noreferrer"
                style={{ color: '#a78bfa', textDecoration: 'none', whiteSpace: 'nowrap' }}>Get key ↗</a>
            </div>
          )}
        </div>

        <div style={{ marginBottom: 10 }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 5 }}>API Key</label>
          <input type="password" value={apiKey}
            onChange={e => {
              const val = e.target.value;
              setApiKey(val);
              const inferred = inferProviderFromKey(val);
              setDetectedProvider(inferred);
              setFetchedModels([]);
              setFetchError('');
            }}
            style={iStyle} placeholder={selectedModel?.keyHint || 'Paste API key here — provider auto-detected'} autoComplete="off" />
        </div>

        {/* Auto-detected provider + fetch button */}
        {detectedProvider && !fetchedModels.length && (
          <div style={{ marginBottom: 10, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{
              fontSize: '0.74rem', padding: '2px 10px', borderRadius: 999,
              background: `${PROVIDER_COLORS[detectedProvider]}22`,
              border: `1px solid ${PROVIDER_COLORS[detectedProvider]}55`,
              color: PROVIDER_COLORS[detectedProvider], fontWeight: 600,
            }}>
              {detectedProvider.charAt(0).toUpperCase() + detectedProvider.slice(1)} key detected
            </span>
            <button
              onClick={async () => {
                setFetching(true); setFetchError('');
                try {
                  const r = await fetch(`${API_BASE}/ai/list-models`, {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ provider: detectedProvider, api_key: apiKey }),
                  });
                  const d = await r.json();
                  if (!r.ok) throw new Error(d.detail || 'Fetch failed');
                  setFetchedModels(d.models || []);
                } catch (e) { setFetchError(e.message); }
                finally { setFetching(false); }
              }}
              disabled={fetching}
              style={{
                fontSize: '0.74rem', background: 'rgba(99,102,241,0.1)',
                border: '1px solid rgba(99,102,241,0.35)', borderRadius: 6,
                color: '#a5b4fc', cursor: fetching ? 'not-allowed' : 'pointer',
                padding: '3px 12px', opacity: fetching ? 0.6 : 1,
              }}>
              {fetching ? 'Fetching…' : 'Fetch available models'}
            </button>
            {fetchError && <span style={{ fontSize: '0.72rem', color: '#f87171' }}>{fetchError}</span>}
          </div>
        )}

        {/* Live model list fetched from provider API */}
        {fetchedModels.length > 0 && (
          <div style={{ marginBottom: 10 }}>
            <label style={{ fontSize: '0.75rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 5 }}>
              Models on your account <span style={{ fontWeight: 400, color: '#4b5563' }}>({fetchedModels.length} found)</span>
            </label>
            <select value={modelName} style={sStyle} onChange={e => setModelName(e.target.value)}>
              <option value="">— Select a model —</option>
              {fetchedModels.map(id => {
                const known = AI_MODELS.find(m => m.id === id);
                return <option key={id} value={id}>{known ? known.label : id}</option>;
              })}
            </select>
            <div style={{ marginTop: 4, fontSize: '0.72rem', color: '#4b5563' }}>
              Fetched live · or pick from the static list below
            </div>
          </div>
        )}

        <div style={{ marginBottom: 10 }}>
          <label style={{ fontSize: '0.75rem', fontWeight: 700, color: '#9ca3af', display: 'block', marginBottom: 5 }}>Label <span style={{ fontWeight: 400, color: '#4b5563' }}>(optional)</span></label>
          <input value={label} onChange={e => setLabel(e.target.value)}
            style={sStyle} placeholder="e.g. Personal, Work" />
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: protect ? 10 : 14 }}>
          <input type="checkbox" id="ai-protect" checked={protect} onChange={e => setProtect(e.target.checked)} style={{ cursor: 'pointer' }} />
          <label htmlFor="ai-protect" style={{ fontSize: '0.83rem', color: '#9ca3af', cursor: 'pointer' }}>🔒 Encrypt with password</label>
        </div>
        {protect && (
          <div style={{ marginBottom: 14 }}>
            <input type="password" value={password} onChange={e => setPassword(e.target.value)}
              style={iStyle} placeholder="Choose a password" />
          </div>
        )}

        {error && <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 7, padding: '7px 12px', color: '#fca5a5', fontSize: '0.82rem', marginBottom: 10 }}>{error}</div>}

        <button onClick={save} disabled={saving}
          style={{ background: saving ? '#1e293b' : 'linear-gradient(135deg,#a78bfa,#22d3ee)', border: 'none', borderRadius: 999, padding: '8px 20px', color: '#0f172a', fontWeight: 700, cursor: saving ? 'not-allowed' : 'pointer', fontSize: '0.87rem', opacity: saving ? 0.7 : 1 }}>
          {saving ? 'Saving…' : 'Save & Activate'}
        </button>
      </div>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function KeyManager() {
  const [tab, setTab] = useState('data');

  const tabs = [
    { id: 'data', label: '📡 Data Providers', desc: 'market data' },
    { id: 'ai',   label: '🤖 AI Models',       desc: 'AI features' },
  ];

  return (
    <div className="view">
      <h2>Key Manager</h2>
      <p>Store multiple API keys for data providers and AI models. Switch the active one anytime — only the active key is used.</p>

      <div style={{ display: 'flex', gap: 10, margin: '1.5rem 0', background: '#0f172a', padding: 6, borderRadius: 14, border: '1px solid #1f2937', width: 'fit-content' }}>
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
            <div style={{ fontSize: '0.67rem', color: tab === t.id ? '#9ca3af' : '#4b5563', fontWeight: 400 }}>for {t.desc}</div>
          </button>
        ))}
      </div>

      <div style={{ background: '#111827', border: '1px solid #1f2937', borderRadius: 16, padding: '1.5rem', maxWidth: 580 }}>
        {tab === 'data' && <DataProviderPanel />}
        {tab === 'ai'   && <AIModelPanel />}
      </div>
    </div>
  );
}
