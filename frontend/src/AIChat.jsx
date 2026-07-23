import { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';

const API_BASE = import.meta.env.VITE_API_BASE || '';

const STRATEGY_ACCENT = {
  solid: '#3b82f6',
  badgeBg: 'rgba(59,130,246,0.15)',
  badgeBorder: 'rgba(59,130,246,0.3)',
  badgeText: '#93c5fd',
  dataText: '#93c5fd',
};

const INDICATOR_ACCENT = {
  solid: '#8b5cf6',
  badgeBg: 'rgba(139,92,246,0.15)',
  badgeBorder: 'rgba(139,92,246,0.3)',
  badgeText: '#c4b5fd',
  dataText: '#d8b4fe',
};

/**
 * Generic AI chat panel shared by the AI Strategy Builder and AI Indicator Builder.
 * All variant-specific behavior (endpoint, colors, i18n keys, request body, result
 * rendering) is supplied via props so each caller stays pixel/flow-identical to its
 * pre-merge standalone component.
 *
 * Props:
 * - endpoint: string - API path (relative to API_BASE) to POST the prompt to.
 * - accent: { solid, badgeBg, badgeBorder, badgeText, dataText } - variant color tokens.
 * - i18nPrefix: string - translation key namespace, e.g. 'aiStrategy'.
 * - headerEmoji: string - emoji shown in the header.
 * - showTemperature: bool - render the creativity/temperature slider in the header.
 * - showWarnings: bool - render a warnings bubble when result.warnings is non-empty.
 * - trackError: bool - also surface caught errors via the inline error banner.
 * - loadingKey: string - i18nPrefix-relative key for the spinner label.
 * - defaultErrorMessage: string - fallback error text when the API gives none.
 * - buildBody(prompt, temperature, lang): object - builds the POST body.
 * - resultMessageParams(result): object - i18next interpolation params for `${i18nPrefix}.generatedResult`.
 * - renderData(msg, t): node - renders the inline result preview under a message bubble.
 * - onResult(result): void - called with the parsed result on success.
 * - welcomeHint(t): Promise<string|null> - optional hook to append text to the welcome message on mount.
 */
export function AIChat({
  endpoint,
  accent,
  i18nPrefix,
  headerEmoji,
  showTemperature = false,
  showWarnings = false,
  trackError = false,
  loadingKey,
  defaultErrorMessage,
  buildBody,
  resultMessageParams,
  renderData,
  onResult,
  welcomeHint,
}) {
  const { t, i18n } = useTranslation();
  const [messages, setMessages] = useState([{ role: 'assistant', content: t(`${i18nPrefix}.welcome`) }]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [temperature, setTemperature] = useState(0.7);
  const [error, setError] = useState('');
  const [modelName, setModelName] = useState(undefined); // undefined = loading, null = none, string = configured
  const messagesEndRef = useRef(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/db/model-keys`)
      .then(r => r.json())
      .then(d => {
        const active = (d.keys || []).find(k => k.active);
        setModelName(active?.model_name || null);
      })
      .catch(() => setModelName(null));
  }, []);

  // Optional variant hook (AI Strategy Builder only) that appends a hint to the welcome message
  useEffect(() => {
    if (!welcomeHint) return;
    welcomeHint(t)
      .then(hint => {
        if (!hint) return;
        setMessages(prev => [{ ...prev[0], content: t(`${i18nPrefix}.welcome`) + hint }, ...prev.slice(1)]);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim()) return;

    const userMessage = input.trim();
    setInput('');
    setError('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildBody(userMessage, temperature, i18n.language))
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || defaultErrorMessage);
      }

      const result = await response.json();

      // Add assistant response with generated result
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: t(`${i18nPrefix}.generatedResult`, resultMessageParams(result)),
          data: result
        }
      ]);

      // Pass generated result to parent
      if (onResult) {
        onResult(result);
      }

      // Show warnings if any
      if (showWarnings && result.warnings && result.warnings.length > 0) {
        const warningMsg = result.warnings.join('\n');
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: `⚠️ Warnings:\n${warningMsg}`, isWarning: true }
        ]);
      }
    } catch (err) {
      const errorMsg = err.message || 'Unknown error';
      if (trackError) setError(errorMsg);
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `Error: ${errorMsg}`, isError: true }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const titleBlock = (
    <>
      <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#e5e7eb', display: 'flex', alignItems: 'center', gap: 8 }}>
        {t(`${i18nPrefix}.title`)}
        {modelName ? (
          <span style={{ fontSize: '0.7rem', fontWeight: 500, padding: '2px 8px', borderRadius: 999, background: accent.badgeBg, border: `1px solid ${accent.badgeBorder}`, color: accent.badgeText }}>
            {modelName}
          </span>
        ) : modelName === null ? (
          <span style={{ fontSize: '0.7rem', fontWeight: 500, padding: '2px 8px', borderRadius: 999, background: 'rgba(245,158,11,0.15)', border: '1px solid rgba(245,158,11,0.3)', color: '#fbbf24' }}>
            {t(`${i18nPrefix}.noModel`)}
          </span>
        ) : null}
      </div>
      <div style={{ fontSize: '0.72rem', color: '#9ca3af' }}>{t(`${i18nPrefix}.subtitle`)}</div>
    </>
  );

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      background: '#0b1120',
      border: '1px solid #1e293b',
      borderRadius: 12,
      overflow: 'hidden'
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px',
        background: '#111827',
        borderBottom: '1px solid #1e293b',
        display: 'flex',
        alignItems: 'center',
        ...(showTemperature ? { justifyContent: 'space-between', gap: 12 } : { gap: 8 })
      }}>
        {showTemperature ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
            <span style={{ fontSize: '1.2rem' }}>{headerEmoji}</span>
            <div>{titleBlock}</div>
          </div>
        ) : (
          <>
            <span style={{ fontSize: '1.2rem' }}>{headerEmoji}</span>
            <div>{titleBlock}</div>
          </>
        )}
        {showTemperature && (
          <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.75rem', color: '#9ca3af' }}>
            {t(`${i18nPrefix}.creativity`)}
            <input
              type="range"
              min="0"
              max="1"
              step="0.1"
              value={temperature}
              onChange={e => setTemperature(parseFloat(e.target.value))}
              style={{ width: 60 }}
            />
            <span style={{ minWidth: 25, color: accent.solid }}>{temperature.toFixed(1)}</span>
          </label>
        )}
      </div>

      {/* Messages */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '12px 16px',
        display: 'flex',
        flexDirection: 'column',
        gap: 10
      }}>
        {messages.map((msg, idx) => (
          <div
            key={idx}
            style={{
              display: 'flex',
              justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start'
            }}
          >
            <div
              style={{
                maxWidth: '85%',
                padding: '10px 14px',
                borderRadius: 10,
                fontSize: '0.85rem',
                lineHeight: '1.4',
                background: msg.role === 'user'
                  ? accent.solid
                  : msg.isError
                    ? '#ef4444'
                    : msg.isWarning
                      ? '#f59e0b'
                      : '#1e293b',
                color: msg.role === 'user' || msg.isError ? '#ffffff' : '#e5e7eb',
                border: msg.isError ? '1px solid #7f1d1d' : msg.isWarning ? '1px solid #92400e' : 'none',
                whiteSpace: 'pre-wrap'
              }}
            >
              {msg.content}
              {msg.data && (
                <div style={{
                  marginTop: 10,
                  padding: '10px',
                  background: 'rgba(0,0,0,0.3)',
                  borderRadius: 6,
                  fontSize: '0.75rem',
                  color: accent.dataText
                }}>
                  {renderData(msg, t)}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#9ca3af', fontSize: '0.85rem' }}>
            <span style={{ animation: 'spin 1s linear infinite' }}>⚙️</span>
            {t(`${i18nPrefix}.${loadingKey}`)}
            <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: '12px 16px',
        borderTop: '1px solid #1e293b',
        background: '#0f1419'
      }}>
        {error && (
          <div style={{
            padding: '8px 12px',
            background: '#7f1d1d',
            borderRadius: 6,
            fontSize: '0.75rem',
            color: '#fecaca',
            marginBottom: 8
          }}>
            {error}
          </div>
        )}
        <div style={{ display: 'flex', gap: 8 }}>
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && (e.preventDefault(), handleSend())}
            placeholder={t(`${i18nPrefix}.placeholder`)}
            disabled={loading}
            style={{
              flex: 1,
              padding: '10px 12px',
              background: '#1e293b',
              border: '1px solid #334155',
              borderRadius: 8,
              color: '#e5e7eb',
              fontSize: '0.85rem',
              outline: 'none'
            }}
          />
          <button
            onClick={handleSend}
            disabled={loading || !input.trim()}
            style={{
              padding: '10px 16px',
              background: loading || !input.trim() ? '#1e293b' : accent.solid,
              border: 'none',
              borderRadius: 8,
              color: loading || !input.trim() ? '#6b7280' : '#ffffff',
              cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
              fontSize: '0.85rem',
              fontWeight: 600
            }}
          >
            {t('common.send')}
          </button>
        </div>
      </div>
    </div>
  );
}

export function AIStrategyChat({ onStrategyGenerated }) {
  return (
    <AIChat
      endpoint="/api/ai/build-strategy"
      accent={STRATEGY_ACCENT}
      i18nPrefix="aiStrategy"
      headerEmoji="🤖"
      showTemperature
      showWarnings
      loadingKey="generatingStrategy"
      defaultErrorMessage="Failed to generate strategy"
      buildBody={(prompt, temperature, lang) => ({ prompt, temperature, language: lang })}
      resultMessageParams={result => ({ name: result.name, count: result.rules.length })}
      renderData={(msg, t) => (
        <>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>{t('aiStrategy.strategyData')}</div>
          <pre style={{ margin: 0, overflow: 'auto', maxHeight: 150 }}>
            {JSON.stringify(msg.data, null, 2)}
          </pre>
        </>
      )}
      welcomeHint={async t => {
        const r = await fetch(`${API_BASE}/api/db/indicators`);
        const d = await r.json();
        const userInds = (d.indicators || []).filter(i => !i.is_builtin);
        if (userInds.length === 0) return null;
        const names = userInds.map(i => `"${i.name}"`).join(', ');
        return t('aiStrategy.customIndicatorHint', { count: userInds.length, names });
      }}
      onResult={onStrategyGenerated}
    />
  );
}

export function AIIndicatorChat({ onIndicatorGenerated }) {
  return (
    <AIChat
      endpoint="/api/ai/build-indicator"
      accent={INDICATOR_ACCENT}
      i18nPrefix="aiIndicator"
      headerEmoji="📊"
      trackError
      loadingKey="generatingIndicator"
      defaultErrorMessage="Failed to generate indicator"
      buildBody={(prompt, temperature, lang) => ({ prompt, language: lang })}
      resultMessageParams={result => ({ name: result.name, description: result.description })}
      renderData={msg => (
        <>
          <div style={{ fontWeight: 600, marginBottom: 4, color: msg.data.color }}>
            ■ {msg.data.name}
          </div>
          <pre style={{ margin: 0, overflow: 'auto', maxHeight: 150 }}>
            {JSON.stringify(msg.data.expr, null, 2)}
          </pre>
        </>
      )}
      onResult={onIndicatorGenerated}
    />
  );
}
