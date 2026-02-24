import { useState, useEffect, useRef } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

// ─── Human-readable building blocks ──────────────────────────────────────────

const BLOCKS = [
  {
    category: "Price Data",
    color: "#22d3ee",
    items: [
      { type: "operand", opType: "price", field: "mid",    label: "Current Price (mid)",    desc: "The average of bid and ask — the 'real' price", emoji: "💰" },
      { type: "operand", opType: "price", field: "bid",    label: "Bid Price",              desc: "What buyers are willing to pay", emoji: "📉" },
      { type: "operand", opType: "price", field: "ask",    label: "Ask Price",              desc: "What sellers want to receive", emoji: "📈" },
      { type: "operand", opType: "price", field: "volume", label: "Volume",                 desc: "How many units were traded", emoji: "📊" },
    ]
  },
  {
    category: "Past Values",
    color: "#f59e0b",
    items: [
      { type: "operand", opType: "lookback", field: "mid", period: 1,  label: "Price N bars ago",   desc: "The price from N candles back — useful for detecting changes", emoji: "⏮️" },
    ]
  },
  {
    category: "Averages",
    color: "#34d399",
    items: [
      { type: "operand", opType: "sma", field: "mid", period: 20, label: "Simple Moving Average (SMA)", desc: "The plain average price over the last N bars. Smooth, but slow to react.", emoji: "〰️" },
      { type: "operand", opType: "ema", field: "mid", period: 20, label: "Exponential Moving Average (EMA)", desc: "Like SMA, but recent prices count more. Faster to react to changes.", emoji: "⚡" },
    ]
  },
  {
    category: "Momentum & Oscillators",
    color: "#a78bfa",
    items: [
      { type: "operand", opType: "rsi", field: "mid", period: 14, label: "RSI (Relative Strength Index)", desc: "Measures how overbought or oversold an asset is. Ranges 0–100. Above 70 = overbought, below 30 = oversold.", emoji: "🔄" },
      { type: "operand", opType: "macd", fast: 12, slow: 26, signal: 9, component: "macd",   label: "MACD Line",         desc: "Shows the difference between two EMAs. Crossing zero signals trend changes.", emoji: "📡" },
      { type: "operand", opType: "macd", fast: 12, slow: 26, signal: 9, component: "signal", label: "MACD Signal Line",  desc: "A smoothed version of the MACD. When MACD crosses above signal, bullish signal.", emoji: "🎯" },
      { type: "operand", opType: "macd", fast: 12, slow: 26, signal: 9, component: "hist",   label: "MACD Histogram",    desc: "The gap between MACD and its signal line. Growing = strengthening trend.", emoji: "📉" },
    ]
  },
  {
    category: "Volatility",
    color: "#f472b6",
    items: [
      { type: "operand", opType: "bollinger", field: "mid", period: 20, std_dev: 2, component: "upper",  label: "Bollinger Upper Band",  desc: "Price ceiling — asset is 'expensive' when near here", emoji: "⬆️" },
      { type: "operand", opType: "bollinger", field: "mid", period: 20, std_dev: 2, component: "lower",  label: "Bollinger Lower Band",  desc: "Price floor — asset is 'cheap' when near here", emoji: "⬇️" },
      { type: "operand", opType: "bollinger", field: "mid", period: 20, std_dev: 2, component: "middle", label: "Bollinger Middle Band",  desc: "The SMA in the center of Bollinger Bands", emoji: "➖" },
      { type: "operand", opType: "bollinger", field: "mid", period: 20, std_dev: 2, component: "width",  label: "Bollinger Width",       desc: "How wide the bands are — high = high volatility", emoji: "↔️" },
      { type: "operand", opType: "bollinger", field: "mid", period: 20, std_dev: 2, component: "pct_b",  label: "Bollinger %B",          desc: "Where price is within the bands (0 = lower, 1 = upper)", emoji: "📍" },
    ]
  },
  {
    category: "Math",
    color: "#6b7280",
    items: [
      { type: "const", value: 0,   label: "Fixed Number",       desc: "A constant number you set manually", emoji: "🔢" },
      { type: "binop", op: "+",    label: "Add  (A + B)",       desc: "Sum of two values", emoji: "➕" },
      { type: "binop", op: "-",    label: "Subtract  (A − B)",  desc: "Difference between two values", emoji: "➖" },
      { type: "binop", op: "*",    label: "Multiply  (A × B)",  desc: "Product of two values", emoji: "✖️" },
      { type: "binop", op: "/",    label: "Divide  (A ÷ B)",    desc: "One value divided by another", emoji: "➗" },
      { type: "unop",  op: "abs",  label: "Absolute Value",     desc: "Removes the minus sign — turns -5 into 5", emoji: "📐" },
      { type: "unop",  op: "sqrt", label: "Square Root",        desc: "√ of a value", emoji: "√" },
    ]
  },
];

// ─── Serialization ────────────────────────────────────────────────────────────
let _nodeId = 100;
const uid = () => String(_nodeId++);

function makeNode(template) {
  const n = { _id: uid(), ...JSON.parse(JSON.stringify(template)) };
  if (n.type === 'binop') { n.left = makeNode({ type: 'const', value: 0 }); n.right = makeNode({ type: 'const', value: 0 }); }
  if (n.type === 'unop')  { n.child = makeNode({ type: 'const', value: 0 }); }
  return n;
}

function serialiseNode(n) {
  if (!n) return { node: 'const', value: 0 };
  if (n.type === 'const')   return { node: 'const', value: parseFloat(n.value) || 0 };
  if (n.type === 'operand') {
    const { _id, type, ...rest } = n;
    return { node: 'operand', operand: { type: n.opType, ...rest, opType: undefined } };
  }
  if (n.type === 'binop') return { node: 'binop', op: n.op, left: serialiseNode(n.left), right: serialiseNode(n.right) };
  if (n.type === 'unop')  return { node: 'unop',  op: n.op, operand: serialiseNode(n.child) };
  return { node: 'const', value: 0 };
}

function inflateNode(raw) {
  if (!raw) return makeNode({ type: 'const', value: 0 });
  if (raw.node === 'const')   return { _id: uid(), type: 'const', value: raw.value ?? 0 };
  if (raw.node === 'operand') { const { type, ...rest } = raw.operand ?? {}; return { _id: uid(), type: 'operand', opType: type, ...rest }; }
  if (raw.node === 'binop')   return { _id: uid(), type: 'binop', op: raw.op, left: inflateNode(raw.left), right: inflateNode(raw.right) };
  if (raw.node === 'unop')    return { _id: uid(), type: 'unop',  op: raw.op, child: inflateNode(raw.operand) };
  return makeNode({ type: 'const', value: 0 });
}

function describeNode(n) {
  if (!n) return '?';
  if (n.type === 'const')   return String(n.value);
  if (n.type === 'operand') {
    const all = BLOCKS.flatMap(b => b.items);
    const match = all.find(i => i.opType === n.opType && (!i.component || i.component === n.component));
    return match?.label ?? n.opType;
  }
  if (n.type === 'binop')   return `(${describeNode(n.left)} ${n.op} ${describeNode(n.right)})`;
  if (n.type === 'unop')    return `${n.op}(${describeNode(n.child)})`;
  return '?';
}

// ─── Param editing for a placed block ────────────────────────────────────────
const PRICE_FIELDS = ['bid', 'ask', 'mid', 'volume'];

function BlockParams({ node, onChange }) {
  if (!node) return null;
  if (node.type === 'const') return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
      <span style={{ fontSize: '0.78rem', color: '#9ca3af' }}>Value:</span>
      <input type="number" value={node.value} style={inputStyle}
        onChange={e => onChange({ ...node, value: parseFloat(e.target.value) || 0 })} />
    </label>
  );

  const set = (k, v) => onChange({ ...node, [k]: v });

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
      {node.opType && ['price', 'lookback', 'sma', 'ema', 'rsi', 'bollinger'].includes(node.opType) && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Price type:</span>
          <select value={node.field || 'mid'} style={selectStyle} onChange={e => set('field', e.target.value)}>
            {PRICE_FIELDS.map(f => <option key={f}>{f}</option>)}
          </select>
        </label>
      )}
      {node.opType && ['lookback','sma','ema','rsi','bollinger'].includes(node.opType) && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Period (bars):</span>
          <input type="number" value={node.period || 14} min={1} style={inputStyle}
            onChange={e => set('period', parseInt(e.target.value) || 1)} />
        </label>
      )}
      {node.opType === 'bollinger' && <>
        <label style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Std Dev:</span>
          <input type="number" value={node.std_dev || 2} min={0.1} step={0.1} style={inputStyle}
            onChange={e => set('std_dev', parseFloat(e.target.value) || 2)} />
        </label>
      </>}
      {node.opType === 'macd' && <>
        <label style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Fast:</span>
          <input type="number" value={node.fast || 12} min={1} style={inputStyle}
            onChange={e => set('fast', parseInt(e.target.value) || 12)} />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Slow:</span>
          <input type="number" value={node.slow || 26} min={1} style={inputStyle}
            onChange={e => set('slow', parseInt(e.target.value) || 26)} />
        </label>
        <label style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ fontSize: '0.75rem', color: '#9ca3af' }}>Signal:</span>
          <input type="number" value={node.signal || 9} min={1} style={inputStyle}
            onChange={e => set('signal', parseInt(e.target.value) || 9)} />
        </label>
      </>}
      {node.type === 'binop' && <>
        <span style={{ fontSize: '0.78rem', color: '#9ca3af' }}>Left:</span>
        <NodeMiniPicker node={node.left} onSet={v => onChange({ ...node, left: v })} />
        <span style={{ fontSize: '0.78rem', color: '#9ca3af' }}>Right:</span>
        <NodeMiniPicker node={node.right} onSet={v => onChange({ ...node, right: v })} />
      </>}
      {node.type === 'unop' && <>
        <span style={{ fontSize: '0.78rem', color: '#9ca3af' }}>Input:</span>
        <NodeMiniPicker node={node.child} onSet={v => onChange({ ...node, child: v })} />
      </>}
    </div>
  );
}

function NodeMiniPicker({ node, onSet }) {
  const [open, setOpen] = useState(false);
  const allItems = BLOCKS.flatMap(b => b.items.map(i => ({ ...i, catColor: b.color })));
  return (
    <div style={{ position: 'relative' }}>
      <button style={{ ...pillStyle, fontSize: '0.72rem', padding: '3px 10px', background: '#1e293b' }}
        onClick={() => setOpen(o => !o)}>
        {describeNode(node)} ▾
      </button>
      {open && (
        <div style={{ position: 'absolute', zIndex: 99, top: '100%', left: 0, background: '#0f172a', border: '1px solid #1f2937', borderRadius: 10, padding: 6, width: 260, maxHeight: 280, overflowY: 'auto', boxShadow: '0 8px 24px rgba(0,0,0,0.5)' }}>
          <div style={{ fontSize: '0.7rem', color: '#6b7280', padding: '2px 4px 6px' }}>Choose a block:</div>
          {allItems.map((item, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 8px', borderRadius: 7, cursor: 'pointer', fontSize: '0.78rem' }}
              onMouseEnter={e => e.currentTarget.style.background = '#1f2937'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              onClick={() => { onSet(makeNode(item)); setOpen(false); }}>
              <span>{item.emoji}</span>
              <span style={{ color: '#e5e7eb' }}>{item.label}</span>
            </div>
          ))}
          <div style={{ borderTop: '1px solid #1f2937', marginTop: 4, paddingTop: 4 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 8px', borderRadius: 7, cursor: 'pointer', fontSize: '0.78rem' }}
              onMouseEnter={e => e.currentTarget.style.background = '#1f2937'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              onClick={() => { onSet(makeNode({ type: 'const', value: 0 })); setOpen(false); }}>
              <span>🔢</span><span style={{ color: '#e5e7eb' }}>Fixed Number</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const inputStyle = { background: '#0f172a', border: '1px solid #334155', borderRadius: 6, padding: '3px 8px', color: '#e5e7eb', fontSize: '0.85rem', width: 70 };
const selectStyle = { background: '#0f172a', border: '1px solid #334155', borderRadius: 6, padding: '3px 8px', color: '#e5e7eb', fontSize: '0.85rem' };
const pillStyle = { background: '#1e293b', border: '1px solid #334155', borderRadius: 999, padding: '5px 14px', color: '#e5e7eb', fontSize: '0.8rem', cursor: 'pointer' };

// ─── Placed block pill in the canvas ─────────────────────────────────────────
function PlacedBlock({ node, onUpdate, onRemove }) {
  const [expanded, setExpanded] = useState(false);
  const all = BLOCKS.flatMap(b => b.items.map(i => ({ ...i, catColor: b.color })));
  const template = all.find(i => {
    if (node.type === 'const') return i.type === 'const';
    if (node.type === 'binop') return i.type === 'binop' && i.op === node.op;
    if (node.type === 'unop')  return i.type === 'unop'  && i.op === node.op;
    return i.opType === node.opType && (!i.component || i.component === node.component);
  });
  const color = template?.catColor ?? '#6b7280';
  const emoji = template?.emoji ?? '🔷';
  const label = template?.label ?? describeNode(node);

  return (
    <div style={{ background: '#111827', border: `1px solid ${color}33`, borderRadius: 12, padding: '10px 14px', marginBottom: 8, transition: 'all 0.2s' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: '1.1rem' }}>{emoji}</span>
        <span style={{ flex: 1, fontWeight: 600, fontSize: '0.9rem', color: '#e5e7eb' }}>{label}</span>
        <button style={{ background: 'transparent', border: 'none', color: '#9ca3af', cursor: 'pointer', fontSize: '0.8rem', padding: '2px 6px' }}
          onClick={() => setExpanded(e => !e)}>
          {expanded ? '▲ less' : '▼ configure'}
        </button>
        <button style={{ background: 'transparent', border: '1px solid #ef444455', borderRadius: 6, color: '#ef4444', cursor: 'pointer', padding: '2px 7px', fontSize: '0.78rem' }}
          onClick={onRemove}>✕</button>
      </div>
      {expanded && (
        <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid #1f2937' }}>
          {template?.desc && <p style={{ fontSize: '0.78rem', color: '#6b7280', margin: '0 0 8px' }}>{template.desc}</p>}
          <BlockParams node={node} onChange={onUpdate} />
        </div>
      )}
    </div>
  );
}

// ─── Drop Zone ────────────────────────────────────────────────────────────────
function DropZone({ onDrop, children, isEmpty }) {
  const [over, setOver] = useState(false);
  return (
    <div
      onDragOver={e => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={e => { e.preventDefault(); setOver(false); onDrop(e); }}
      style={{
        minHeight: isEmpty ? 100 : 'auto',
        border: over ? '2px dashed #22d3ee' : '2px dashed transparent',
        borderRadius: 12,
        background: over ? 'rgba(34,211,238,0.05)' : 'transparent',
        transition: 'all 0.2s',
        padding: isEmpty ? '0' : '0',
      }}>
      {isEmpty && !over && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 100, color: '#374151', fontSize: '0.85rem', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: '1.5rem' }}>🧩</span>
          <span>Drag blocks here to build your indicator</span>
        </div>
      )}
      {children}
    </div>
  );
}

// ─── Draggable block in sidebar palette ──────────────────────────────────────
function PaletteItem({ item, catColor }) {
  return (
    <div
      draggable
      onDragStart={e => e.dataTransfer.setData('block', JSON.stringify(item))}
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 10, padding: '9px 12px',
        background: '#0f172a', border: `1px solid ${catColor}30`, borderRadius: 10,
        cursor: 'grab', marginBottom: 6, transition: 'all 0.15s', userSelect: 'none',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = '#1e293b'; e.currentTarget.style.borderColor = catColor; }}
      onMouseLeave={e => { e.currentTarget.style.background = '#0f172a'; e.currentTarget.style.borderColor = `${catColor}30`; }}>
      <span style={{ fontSize: '1.1rem', flexShrink: 0 }}>{item.emoji}</span>
      <div>
        <div style={{ fontSize: '0.82rem', fontWeight: 600, color: '#e5e7eb', lineHeight: 1.3 }}>{item.label}</div>
        <div style={{ fontSize: '0.72rem', color: '#6b7280', lineHeight: 1.4, marginTop: 2 }}>{item.desc}</div>
      </div>
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────
let _indId = 1;

export default function IndicatorBuilder() {
  const [indicators, setIndicators] = useState([]);
  const [activeId, setActiveId]     = useState(null);
  const [loading, setLoading]       = useState(false);
  const [saving, setSaving]         = useState(false);
  const [error, setError]           = useState('');
  const [filter, setFilter]         = useState('');

  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE}/db/indicators`)
      .then(r => r.json())
      .then(d => {
        const loaded = (d.indicators || []).map(ind => ({
          _id: String(_indId++),
          name: ind.name,
          description: ind.description || '',
          color: ind.color || '#22d3ee',
          blocks: ind.expr ? [inflateNode(ind.expr)] : [],
        }));
        setIndicators(loaded);
        if (loaded.length) setActiveId(loaded[0]._id);
      })
      .catch(() => setError('Failed to load indicators'))
      .finally(() => setLoading(false));
  }, []);

  const active = indicators.find(i => i._id === activeId);

  const addIndicator = () => {
    const ind = { _id: String(_indId++), name: 'My Indicator', description: '', color: '#22d3ee', blocks: [] };
    setIndicators(p => [...p, ind]);
    setActiveId(ind._id);
  };

  const updateActive = upd => setIndicators(p => p.map(i => i._id === upd._id ? upd : i));
  const deleteIndicator = id => {
    const rest = indicators.filter(i => i._id !== id);
    setIndicators(rest);
    if (activeId === id) setActiveId(rest[0]?._id ?? null);
  };

  const handleDrop = e => {
    try {
      const raw = JSON.parse(e.dataTransfer.getData('block'));
      const node = makeNode(raw);
      updateActive({ ...active, blocks: [...active.blocks, node] });
    } catch {}
  };

  const removeBlock = id => updateActive({ ...active, blocks: active.blocks.filter(b => b._id !== id) });
  const updateBlock = updated => updateActive({ ...active, blocks: active.blocks.map(b => b._id === updated._id ? updated : b) });

  // For save, combine multiple blocks with binop + chain or just use first
  const buildExpr = blocks => {
    if (!blocks.length) return null;
    if (blocks.length === 1) return serialiseNode(blocks[0]);
    // chain them with + by default; user can change math nodes
    return blocks.slice(1).reduce((acc, b) => ({ node: 'binop', op: '+', left: acc, right: serialiseNode(b) }), serialiseNode(blocks[0]));
  };

  const save = async () => {
    const invalid = indicators.find(i => !i.name.trim());
    if (invalid) { setError('All indicators need a name.'); return; }
    setError(''); setSaving(true);
    try {
      const payload = indicators.map(ind => ({
        name: ind.name,
        description: ind.description,
        color: ind.color,
        expr: buildExpr(ind.blocks),
      }));
      await fetch(`${API_BASE}/db/indicators`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ indicators: payload }) });
      alert('Indicators saved!');
    } catch { setError('Failed to save.'); }
    finally { setSaving(false); }
  };

  const COLORS = ['#22d3ee','#34d399','#a78bfa','#fb923c','#f472b6','#f59e0b','#38bdf8'];
  const filteredBlocks = BLOCKS.map(cat => ({
    ...cat,
    items: cat.items.filter(i => !filter || i.label.toLowerCase().includes(filter.toLowerCase()) || i.desc.toLowerCase().includes(filter.toLowerCase())),
  })).filter(cat => cat.items.length > 0);

  return (
    <div className="view">
      <style>{`
        .ib2-wrap { display: flex; gap: 16px; align-items: flex-start; margin-top: 1.5rem; }
        .ib2-palette { flex-shrink: 0; width: 280px; position: sticky; top: 0; max-height: calc(100vh - 80px); overflow-y: auto; }
        .ib2-main { flex: 1; min-width: 0; }
        @media (max-width: 700px) { .ib2-wrap { flex-direction: column; } .ib2-palette { width: 100%; position: static; max-height: 320px; } }
      `}</style>
      <h2>Indicator Builder</h2>
      <p>Drag building blocks onto your indicator canvas. Each indicator is a reusable signal you can reference in your strategies.</p>

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <button style={{ ...pillStyle, background: 'linear-gradient(135deg,#6366f1,#22d3ee)', color: '#0f172a', fontWeight: 700, border: 'none' }} onClick={addIndicator}>
          + New Indicator
        </button>
        {indicators.map(ind => (
          <button key={ind._id}
            style={{ ...pillStyle, background: ind._id === activeId ? ind.color + '22' : '#0f172a', borderColor: ind._id === activeId ? ind.color : '#334155', color: ind._id === activeId ? ind.color : '#9ca3af', display: 'flex', alignItems: 'center', gap: 6 }}
            onClick={() => setActiveId(ind._id)}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: ind.color, display: 'inline-block' }} />
            {ind.name}
          </button>
        ))}
        {indicators.length > 0 && (
          <button style={{ ...pillStyle, background: saving ? '#1e293b' : 'linear-gradient(135deg,#22d3ee,#34d399)', color: '#0f172a', fontWeight: 700, border: 'none', marginLeft: 'auto' }}
            onClick={save} disabled={saving}>{saving ? 'Saving…' : 'Save All'}</button>
        )}
      </div>

      {error && <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', borderRadius: 10, padding: '10px 14px', color: '#fca5a5', marginBottom: 14, fontSize: '0.87rem' }}>{error}</div>}

      {loading ? <div style={{ color: '#6b7280', textAlign: 'center', padding: 40 }}>Loading…</div> : (
        <div className="ib2-wrap">
          {/* Palette */}
          <aside className="ib2-palette">
            <div style={{ background: '#111827', border: '1px solid #1f2937', borderRadius: 16, padding: '1rem', overflow: 'hidden' }}>
              <div style={{ fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#6b7280', marginBottom: 10 }}>Building Blocks</div>
              <input placeholder="Search blocks…" value={filter} onChange={e => setFilter(e.target.value)}
                style={{ width: '100%', background: '#0f172a', border: '1px solid #334155', borderRadius: 8, padding: '6px 10px', color: '#e5e7eb', fontSize: '0.82rem', marginBottom: 12, outline: 'none' }} />
              {filteredBlocks.map(cat => (
                <div key={cat.category} style={{ marginBottom: 14 }}>
                  <div style={{ fontSize: '0.68rem', fontWeight: 700, letterSpacing: '0.08em', textTransform: 'uppercase', color: cat.color, marginBottom: 6 }}>{cat.category}</div>
                  {cat.items.map((item, i) => <PaletteItem key={i} item={item} catColor={cat.color} />)}
                </div>
              ))}
            </div>
          </aside>

          {/* Canvas */}
          <div className="ib2-main">
            {!active ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: 200, color: '#4b5563', gap: 8 }}>
                <span style={{ fontSize: '2rem' }}>🧩</span>
                <span>Create a new indicator to get started</span>
              </div>
            ) : (
              <div style={{ background: '#111827', border: '1px solid #1f2937', borderRadius: 16, padding: '1.25rem', boxShadow: '0 4px 20px rgba(0,0,0,0.3)' }}>
                {/* Header */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
                  <input
                    value={active.name}
                    onChange={e => updateActive({ ...active, name: e.target.value })}
                    style={{ flex: 1, minWidth: 120, background: 'transparent', border: 'none', color: '#e5e7eb', fontSize: '1.1rem', fontWeight: 700, outline: 'none' }}
                    placeholder="Indicator name…" />
                  <div style={{ display: 'flex', gap: 5 }}>
                    {COLORS.map(c => (
                      <div key={c} onClick={() => updateActive({ ...active, color: c })}
                        style={{ width: 18, height: 18, borderRadius: 4, background: c, cursor: 'pointer', border: active.color === c ? '2px solid #fff' : '2px solid transparent', transition: 'all 0.15s' }} />
                    ))}
                  </div>
                  <button onClick={() => deleteIndicator(active._id)}
                    style={{ background: 'transparent', border: '1px solid #ef444455', borderRadius: 8, color: '#ef4444', cursor: 'pointer', padding: '4px 10px', fontSize: '0.78rem' }}>Delete</button>
                </div>

                <input
                  value={active.description}
                  onChange={e => updateActive({ ...active, description: e.target.value })}
                  style={{ width: '100%', background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, padding: '7px 12px', color: '#9ca3af', fontSize: '0.85rem', outline: 'none', marginBottom: 16 }}
                  placeholder="Optional description…" />

                {/* Formula preview */}
                {active.blocks.length > 0 && (
                  <div style={{ background: '#0b1120', border: '1px dashed #334155', borderRadius: 10, padding: '8px 14px', marginBottom: 14, fontSize: '0.8rem', color: '#93c5fd', fontFamily: 'ui-monospace, monospace' }}>
                    {active.blocks.map((b, i) => (
                      <span key={b._id}>{i > 0 ? <span style={{ color: '#f59e0b' }}> + </span> : null}{describeNode(b)}</span>
                    ))}
                  </div>
                )}

                {/* Drop zone */}
                <DropZone onDrop={handleDrop} isEmpty={active.blocks.length === 0}>
                  {active.blocks.map(b => (
                    <PlacedBlock key={b._id} node={b}
                      onUpdate={updateBlock}
                      onRemove={() => removeBlock(b._id)} />
                  ))}
                </DropZone>

                {active.blocks.length > 1 && (
                  <p style={{ fontSize: '0.75rem', color: '#6b7280', marginTop: 8 }}>
                    💡 Multiple blocks are combined with addition by default. Use a "Subtract/Multiply/Divide" math block to change how they combine.
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}