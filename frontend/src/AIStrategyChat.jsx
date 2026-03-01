import { useState, useRef, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

const WELCOME_BASE = 'Hi! Describe your trading strategy in plain English and I\'ll convert it to rules. For example: "Buy when a 20-day EMA crosses above a 50-day EMA. Sell when RSI exceeds 70."';

export function AIStrategyChat({ onStrategyGenerated }) {
  const [messages, setMessages] = useState([{ role: 'assistant', content: WELCOME_BASE }]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [temperature, setTemperature] = useState(0.7);
  const [error, setError] = useState('');
  const [modelName, setModelName] = useState(undefined); // undefined = loading, null = none, string = configured
  const messagesEndRef = useRef(null);

  // Fix: correct endpoint for model keys
  useEffect(() => {
    fetch(`${API_BASE}/db/model-keys`)
      .then(r => r.json())
      .then(d => {
        const active = (d.keys || []).find(k => k.active);
        setModelName(active?.model_name || null);
      })
      .catch(() => setModelName(null));
  }, []);

  // Load custom indicators and append a hint to the welcome message
  useEffect(() => {
    fetch(`${API_BASE}/db/indicators`)
      .then(r => r.json())
      .then(d => {
        const userInds = (d.indicators || []).filter(i => !i.is_builtin);
        if (userInds.length === 0) return;
        const names = userInds.map(i => `"${i.name}"`).join(', ');
        const hint = `\n\nYou have ${userInds.length} custom indicator${userInds.length > 1 ? 's' : ''}: ${names}. Reference them by name in your prompt. To use non-default parameter values, mention them explicitly — e.g. "use RSI Oversold with period 10 and threshold 25".`;
        setMessages(prev => [{ ...prev[0], content: WELCOME_BASE + hint }, ...prev.slice(1)]);
      })
      .catch(() => {});
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
      const response = await fetch(`${API_BASE}/ai/build-strategy`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: userMessage,
          temperature: temperature
        })
      });

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Failed to generate strategy');
      }

      const result = await response.json();

      // Add assistant response with generated strategy
      setMessages(prev => [
        ...prev,
        {
          role: 'assistant',
          content: `Generated "${result.name}" strategy with ${result.rules.length} rule(s)`,
          data: result
        }
      ]);

      // Pass generated strategy to parent
      if (onStrategyGenerated) {
        onStrategyGenerated(result);
      }

      // Show warnings if any
      if (result.warnings && result.warnings.length > 0) {
        const warningMsg = result.warnings.join('\n');
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: `⚠️ Warnings:\n${warningMsg}`, isWarning: true }
        ]);
      }
    } catch (err) {
      const errorMsg = err.message || 'Unknown error';
      setError(errorMsg);
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: `Error: ${errorMsg}`, isError: true }
      ]);
    } finally {
      setLoading(false);
    }
  };

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
        justifyContent: 'space-between',
        gap: 12
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1 }}>
          <span style={{ fontSize: '1.2rem' }}>🤖</span>
          <div>
            <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#e5e7eb', display: 'flex', alignItems: 'center', gap: 8 }}>
              AI Strategy Builder
              {modelName ? (
                <span style={{ fontSize: '0.7rem', fontWeight: 500, padding: '2px 8px', borderRadius: 999, background: 'rgba(59,130,246,0.15)', border: '1px solid rgba(59,130,246,0.3)', color: '#93c5fd' }}>
                  {modelName}
                </span>
              ) : modelName === null ? (
                <span style={{ fontSize: '0.7rem', fontWeight: 500, padding: '2px 8px', borderRadius: 999, background: 'rgba(245,158,11,0.15)', border: '1px solid rgba(245,158,11,0.3)', color: '#fbbf24' }}>
                  No AI model configured
                </span>
              ) : null}
            </div>
            <div style={{ fontSize: '0.72rem', color: '#9ca3af' }}>Natural language → Rules</div>
          </div>
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.75rem', color: '#9ca3af' }}>
          Creativity:
          <input
            type="range"
            min="0"
            max="1"
            step="0.1"
            value={temperature}
            onChange={e => setTemperature(parseFloat(e.target.value))}
            style={{ width: 60 }}
          />
          <span style={{ minWidth: 25, color: '#3b82f6' }}>{temperature.toFixed(1)}</span>
        </label>
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
                  ? '#3b82f6'
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
                  color: '#93c5fd'
                }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>Strategy Data:</div>
                  <pre style={{ margin: 0, overflow: 'auto', maxHeight: 150 }}>
                    {JSON.stringify(msg.data, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#9ca3af', fontSize: '0.85rem' }}>
            <span style={{ animation: 'spin 1s linear infinite' }}>⚙️</span>
            Generating strategy…
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
            placeholder="Describe your strategy…"
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
              background: loading || !input.trim() ? '#1e293b' : '#3b82f6',
              border: 'none',
              borderRadius: 8,
              color: loading || !input.trim() ? '#6b7280' : '#ffffff',
              cursor: loading || !input.trim() ? 'not-allowed' : 'pointer',
              fontSize: '0.85rem',
              fontWeight: 600
            }}
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
