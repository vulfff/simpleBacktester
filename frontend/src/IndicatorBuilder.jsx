import { useState, useEffect } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

// ─── Expression tree schema ───────────────────────────────────────────────────
// Mirrors indicator_registry.py node types exactly.

const PRICE_FIELDS = ["bid", "ask", "mid", "volume"];

const UNARY_OPS  = ["neg", "abs", "sqrt", "log"];
const BINARY_OPS = ["+", "-", "*", "/", "**", "%"];
const COND_OPS   = [">", "<", ">=", "<=", "==", "!="];

// Operand sub-types available inside an expression node
const OPERAND_TYPES = {
  price:     { label: "Price",      color: "#22d3ee", params: [{ name: "field",  type: "select",  label: "Field",  default: "mid", options: PRICE_FIELDS }] },
  lookback:  { label: "N bars ago", color: "#f59e0b", params: [{ name: "field",  type: "select",  label: "Field",  default: "mid", options: PRICE_FIELDS },
                                                                 { name: "period",type: "integer", label: "Bars",   default: 1,    min: 1 }] },
  sma:       { label: "SMA",        color: "#34d399", params: [{ name: "field",  type: "select",  label: "Field",  default: "mid", options: PRICE_FIELDS },
                                                                 { name: "period",type: "integer", label: "Period", default: 20,   min: 2 }] },
  ema:       { label: "EMA",        color: "#38bdf8", params: [{ name: "field",  type: "select",  label: "Field",  default: "mid", options: PRICE_FIELDS },
                                                                 { name: "period",type: "integer", label: "Period", default: 20,   min: 2 }] },
  rsi:       { label: "RSI",        color: "#a78bfa", params: [{ name: "field",  type: "select",  label: "Field",  default: "mid", options: PRICE_FIELDS },
                                                                 { name: "period",type: "integer", label: "Period", default: 14,   min: 2 }] },
  bollinger: { label: "Bollinger",  color: "#f472b6", params: [{ name: "field",  type: "select",  label: "Field",  default: "mid", options: PRICE_FIELDS },
                                                                 { name: "period",type: "integer", label: "Period", default: 20,   min: 2 },
                                                                 { name: "std_dev",type: "number", label: "σ",      default: 2 },
                                                                 { name: "component", type: "select", label: "Band", default: "upper", options: ["upper","middle","lower","width","pct_b"] }] },
  macd:      { label: "MACD",       color: "#fb923c", params: [{ name: "fast",   type: "integer", label: "Fast",   default: 12,   min: 1 },
                                                                 { name: "slow",   type: "integer", label: "Slow",   default: 26,   min: 1 },
                                                                 { name: "signal", type: "integer", label: "Signal", default: 9,    min: 1 },
                                                                 { name: "component", type: "select", label: "Output", default: "macd", options: ["macd","signal","hist"] }] },
};

// ─── Node factory helpers ─────────────────────────────────────────────────────
let _id = 1;
const uid = () => String(_id++);

function makeConst(value = 0)   { return { _id: uid(), node: "const", value }; }
function makeOperand(type = "price") {
  const params = {};
  (OPERAND_TYPES[type]?.params ?? []).forEach(p => { params[p.name] = p.default; });
  return { _id: uid(), node: "operand", opType: type, ...params };
}
function makeBinop(op = "+")    { return { _id: uid(), node: "binop", op, left: makeConst(0), right: makeConst(0) }; }
function makeUnop(op = "abs")   { return { _id: uid(), node: "unop",  op, operand: makeConst(0) }; }
function makeClamp()            { return { _id: uid(), node: "clamp", value: makeConst(0), lo: makeConst(0), hi: makeConst(1) }; }
function makeIfelse()           { return { _id: uid(), node: "ifelse", cond_left: makeConst(0), cond_op: ">", cond_right: makeConst(0), then: makeConst(1), else_: makeConst(0) }; }

function defaultNode() { return makeOperand("price"); }

// Convert internal tree (with _id, opType) → wire format for the backend
function serialiseNode(n) {
  if (!n) return null;
  if (n.node === "const")   return { node: "const",   value: n.value };
  if (n.node === "operand") {
    const { _id, node, opType, ...params } = n;
    return { node: "operand", operand: { type: opType, ...params } };
  }
  if (n.node === "binop")   return { node: "binop",  op: n.op, left: serialiseNode(n.left), right: serialiseNode(n.right) };
  if (n.node === "unop")    return { node: "unop",   op: n.op, operand: serialiseNode(n.operand) };
  if (n.node === "clamp")   return { node: "clamp",  value: serialiseNode(n.value), lo: serialiseNode(n.lo), hi: serialiseNode(n.hi) };
  if (n.node === "ifelse")  return { node: "ifelse", cond_left: serialiseNode(n.cond_left), cond_op: n.cond_op, cond_right: serialiseNode(n.cond_right), then: serialiseNode(n.then), else_: serialiseNode(n.else_) };
  return null;
}

// Human-readable summary of a node (for the list preview)
function describeNode(n, depth = 0) {
  if (!n || depth > 3) return "…";
  if (n.node === "const")   return String(n.value);
  if (n.node === "operand") {
    const schema = OPERAND_TYPES[n.opType];
    if (!schema) return n.opType;
    const periodPart = n.period ? `(${n.period})` : "";
    const fieldPart  = n.field  ? `.${n.field}`   : "";
    return `${schema.label}${periodPart}${fieldPart}`;
  }
  if (n.node === "binop")  return `(${describeNode(n.left, depth+1)} ${n.op} ${describeNode(n.right, depth+1)})`;
  if (n.node === "unop")   return `${n.op}(${describeNode(n.operand, depth+1)})`;
  if (n.node === "clamp")  return `clamp(${describeNode(n.value, depth+1)})`;
  if (n.node === "ifelse") return `if(${describeNode(n.cond_left, depth+1)} ${n.cond_op} ${describeNode(n.cond_right, depth+1)})`;
  return "?";
}

const NODE_TYPES = [
  { value: "operand", label: "Indicator / Field" },
  { value: "const",   label: "Constant" },
  { value: "binop",   label: "Binary Op  (a ○ b)" },
  { value: "unop",    label: "Unary Op   (f(a))" },
  { value: "clamp",   label: "Clamp" },
  { value: "ifelse",  label: "If / Else" },
];

function changeNodeType(n, newType) {
  if (newType === "const")   return makeConst();
  if (newType === "operand") return makeOperand();
  if (newType === "binop")   return makeBinop();
  if (newType === "unop")    return makeUnop();
  if (newType === "clamp")   return makeClamp();
  if (newType === "ifelse")  return makeIfelse();
  return n;
}

// ─── Styles ──────────────────────────────────────────────────────────────────
const css = `
  .ib-wrap { display: flex; gap: 1rem; align-items: flex-start; }

  /* sidebar */
  .ib-sidebar {
    flex-shrink: 0; width: 220px;
    background: #0f172a; border: 1px solid #1f2937; border-radius: 16px;
    padding: 1rem; display: flex; flex-direction: column; gap: 0.5rem;
    position: sticky; top: 0;
  }
  .ib-sidebar-label {
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
    color: #6b7280; padding-bottom: 0.25rem; border-bottom: 1px solid #1f2937; margin-bottom: 0.25rem;
  }
  .ib-ind-item {
    display: flex; align-items: center; gap: 8px; padding: 0.45rem 0.6rem;
    border-radius: 8px; cursor: pointer; transition: background 0.15s; font-size: 0.8rem; color: #9ca3af;
  }
  .ib-ind-item:hover  { background: #1f2937; color: #e5e7eb; }
  .ib-ind-item.active { background: rgba(34,211,238,0.1); color: #22d3ee; }
  .ib-ind-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
  .ib-ind-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ib-ind-del {
    background: transparent; border: none; color: #4b5563; cursor: pointer;
    font-size: 0.9rem; padding: 0 2px; line-height: 1; transition: color 0.15s;
  }
  .ib-ind-del:hover { color: #f87171; }

  /* editor area */
  .ib-editor { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1rem; }

  /* new indicator form */
  .ib-new-card {
    background: #111827; border: 1px solid #1f2937; border-radius: 16px; overflow: hidden;
    box-shadow: 0 4px 16px rgba(0,0,0,0.2);
  }
  .ib-new-header {
    display: flex; align-items: center; gap: 0.75rem; padding: 0.9rem 1.25rem;
    background: #0f172a; border-bottom: 1px solid #1f2937; flex-wrap: wrap;
  }
  .ib-new-name-input {
    flex: 1; min-width: 140px; background: transparent; border: none;
    color: #e5e7eb; font-family: inherit; font-size: 0.95rem; font-weight: 600; outline: none;
  }
  .ib-new-name-input:focus { color: #22d3ee; }
  .ib-new-name-input::placeholder { color: #374151; }

  /* color swatch picker */
  .ib-color-row { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
  .ib-color-swatch {
    width: 18px; height: 18px; border-radius: 4px; cursor: pointer; border: 2px solid transparent;
    transition: border-color 0.15s; flex-shrink: 0;
  }
  .ib-color-swatch.selected { border-color: #e5e7eb; }

  .ib-desc-input {
    width: 100%; background: #0f172a; border: 1px solid #334155; border-radius: 8px;
    padding: 0.4rem 0.65rem; color: #9ca3af; font-family: inherit; font-size: 0.8rem; outline: none;
    transition: border-color 0.15s;
  }
  .ib-desc-input:focus { border-color: #22d3ee; color: #e5e7eb; }

  .ib-expr-section { padding: 1rem 1.25rem; }
  .ib-section-label {
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
    color: #6b7280; margin-bottom: 0.75rem;
  }

  /* ── Expression tree nodes ── */
  .ib-node {
    background: #0b1120; border: 1px solid #1e293b; border-radius: 10px;
    overflow: hidden; transition: border-color 0.15s;
  }
  .ib-node:hover { border-color: #334155; }
  .ib-node-header {
    display: flex; align-items: center; gap: 0.5rem; padding: 0.5rem 0.75rem;
    background: #0f172a; border-bottom: 1px solid #1e293b; flex-wrap: wrap;
  }
  .ib-node-type-tag {
    font-size: 0.6rem; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
    padding: 0.15rem 0.5rem; border-radius: 4px;
    background: rgba(34,211,238,0.08); color: #22d3ee; border: 1px solid rgba(34,211,238,0.2);
  }
  .ib-node-type-select {
    background: #111827; border: 1px solid #1e293b; border-radius: 6px;
    padding: 0.2rem 0.5rem; color: #9ca3af; font-family: inherit; font-size: 0.75rem;
    outline: none; cursor: pointer; transition: border-color 0.15s, color 0.15s;
  }
  .ib-node-type-select:focus, .ib-node-type-select:hover { border-color: #334155; color: #e5e7eb; }
  .ib-node-body { padding: 0.65rem 0.75rem; display: flex; flex-direction: column; gap: 0.5rem; }

  .ib-field-row { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; }
  .ib-field-label { font-size: 0.7rem; color: #6b7280; white-space: nowrap; min-width: 52px; }
  .ib-field-select, .ib-field-input {
    background: #111827; border: 1px solid #1e293b; border-radius: 6px;
    padding: 0.25rem 0.5rem; color: #e5e7eb; font-family: inherit; font-size: 0.8rem;
    outline: none; transition: border-color 0.15s;
  }
  .ib-field-select:focus, .ib-field-input:focus { border-color: #22d3ee; }
  .ib-field-input[type=number] { width: 76px; }

  /* operand tag colours */
  .ib-operand-tag {
    font-size: 0.6rem; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase;
    padding: 0.15rem 0.5rem; border-radius: 4px; white-space: nowrap;
  }

  /* child node indent */
  .ib-child-slot { display: flex; flex-direction: column; gap: 0.35rem; }
  .ib-child-label { font-size: 0.65rem; color: #4b5563; padding-left: 2px; letter-spacing: 0.05em; }
  .ib-child-indent { padding-left: 1rem; border-left: 1px solid #1e293b; }

  /* op selector pill */
  .ib-op-pill {
    display: inline-flex; align-items: center; gap: 4px;
  }
  .ib-op-select {
    background: #1e293b; border: 1px solid #334155; border-radius: 6px;
    padding: 0.2rem 0.5rem; color: #22d3ee; font-family: inherit; font-size: 0.8rem;
    font-weight: 600; outline: none; cursor: pointer; transition: border-color 0.15s;
  }
  .ib-op-select:focus { border-color: #22d3ee; }

  /* topbar / buttons shared with rule builder */
  .ib-topbar { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .ib-topbar-sep { flex: 1; }
  .ib-btn {
    background: #1e293b; border: 1px solid #334155; border-radius: 10px;
    padding: 0.45rem 1rem; color: #e5e7eb; font-family: inherit; font-size: 0.85rem;
    cursor: pointer; transition: border-color 0.15s, color 0.15s;
  }
  .ib-btn:hover { border-color: #22d3ee; color: #22d3ee; }
  .ib-btn-primary {
    background: linear-gradient(135deg, #6366f1, #22d3ee); border: none; border-radius: 999px;
    padding: 0.5rem 1.4rem; color: #0f172a; font-family: inherit; font-size: 0.85rem;
    font-weight: 600; cursor: pointer; transition: transform 0.15s, opacity 0.15s;
  }
  .ib-btn-primary:hover { transform: translateY(-1px); opacity: 0.9; }
  .ib-btn-primary:disabled { opacity: 0.55; cursor: not-allowed; transform: none; }
  .ib-btn-sm {
    background: #1e293b; border: 1px solid #334155; border-radius: 8px;
    padding: 0.3rem 0.75rem; color: #e5e7eb; font-family: inherit; font-size: 0.8rem;
    cursor: pointer; transition: border-color 0.15s, color 0.15s;
  }
  .ib-btn-sm:hover { border-color: #22d3ee; color: #22d3ee; }

  .ib-remove-ind {
    background: transparent; border: 1px solid rgba(248,113,113,0.3); border-radius: 6px;
    padding: 0.25rem 0.65rem; color: #f87171; font-family: inherit; font-size: 0.75rem;
    cursor: pointer; transition: background 0.15s;
  }
  .ib-remove-ind:hover { background: rgba(248,113,113,0.12); }

  .ib-empty { text-align: center; padding: 3rem 1rem; color: #4b5563; font-size: 0.9rem; }
  .ib-empty-icon { font-size: 2rem; margin-bottom: 0.75rem; opacity: 0.4; }

  .ib-json-panel {
    background: #0b1120; border: 1px dashed #334155; border-radius: 12px;
    padding: 1rem 1.25rem; position: relative; margin-bottom: 1rem;
  }
  .ib-json-label { font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: #6b7280; margin-bottom: 0.5rem; }
  .ib-json-pre {
    font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 0.75rem; color: #93c5fd;
    white-space: pre; overflow-x: auto; max-height: 160px; overflow-y: auto; line-height: 1.6;
  }
  .ib-json-copy { position: absolute; top: 0.75rem; right: 0.75rem; }

  .ib-expr-preview {
    font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 0.75rem;
    color: #6b7280; padding: 0.3rem 0; letter-spacing: 0.02em;
  }
  .ib-add-node-btn {
    background: transparent; border: 1px dashed #1e293b; border-radius: 8px;
    padding: 0.45rem 1rem; color: #4b5563; font-family: inherit; font-size: 0.8rem;
    cursor: pointer; transition: border-color 0.15s, color 0.15s; width: 100%; text-align: left; margin-top: 0.5rem;
  }
  .ib-add-node-btn:hover { border-color: #22d3ee; color: #22d3ee; }

  .ib-error { background: rgba(248,113,113,0.1); border: 1px solid rgba(248,113,113,0.3); border-radius: 8px; padding: 0.6rem 0.9rem; color: #fca5a5; font-size: 0.8rem; }
`;

const PALETTE = ["#22d3ee","#34d399","#f59e0b","#a78bfa","#f472b6","#fb923c","#38bdf8","#f87171"];

// ─── Recursive Node Editor ────────────────────────────────────────────────────

function NodeEditor({ node, onChange, depth = 0 }) {
  if (!node) return null;

  const handleTypeChange = (newType) => onChange(changeNodeType(node, newType));
  const indent = depth > 0;

  const header = (
    <div className="ib-node-header">
      <span className="ib-node-type-tag">{node.node}</span>
      <select className="ib-node-type-select" value={node.node} onChange={e => handleTypeChange(e.target.value)}>
        {NODE_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
      </select>
    </div>
  );

  let body = null;

  // ── Constant ──
  if (node.node === "const") {
    body = (
      <div className="ib-field-row">
        <span className="ib-field-label">Value</span>
        <input
          className="ib-field-input"
          type="number"
          step="any"
          value={node.value}
          onChange={e => onChange({ ...node, value: parseFloat(e.target.value) || 0 })}
        />
      </div>
    );
  }

  // ── Operand (indicator/field) ──
  if (node.node === "operand") {
    const schema = OPERAND_TYPES[node.opType];
    const c = schema?.color ?? "#6b7280";
    body = (
      <>
        <div className="ib-field-row">
          <span className="ib-field-label">Type</span>
          <span className="ib-operand-tag" style={{ background: c + "1a", color: c, border: `1px solid ${c}40` }}>
            {schema?.label ?? node.opType}
          </span>
          <select
            className="ib-field-select"
            value={node.opType}
            onChange={e => {
              const t = e.target.value;
              const p = {};
              (OPERAND_TYPES[t]?.params ?? []).forEach(x => { p[x.name] = x.default; });
              onChange({ _id: node._id, node: "operand", opType: t, ...p });
            }}
          >
            {Object.entries(OPERAND_TYPES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
          </select>
        </div>
        {schema?.params.map(p => (
          <div className="ib-field-row" key={p.name}>
            <span className="ib-field-label">{p.label}</span>
            {p.type === "select" ? (
              <select className="ib-field-select" value={node[p.name] ?? p.default} onChange={e => onChange({ ...node, [p.name]: e.target.value })}>
                {p.options.map(o => <option key={o} value={o}>{o}</option>)}
              </select>
            ) : (
              <input
                className="ib-field-input"
                type="number"
                value={node[p.name] ?? p.default}
                min={p.min}
                step={p.type === "integer" ? 1 : 0.01}
                onChange={e => onChange({ ...node, [p.name]: p.type === "integer" ? parseInt(e.target.value) : parseFloat(e.target.value) })}
              />
            )}
          </div>
        ))}
      </>
    );
  }

  // ── Binary op ──
  if (node.node === "binop") {
    body = (
      <>
        <div className="ib-field-row">
          <span className="ib-field-label">Operator</span>
          <div className="ib-op-pill">
            {BINARY_OPS.map(op => (
              <button
                key={op}
                className="ib-btn-sm"
                onClick={() => onChange({ ...node, op })}
                style={node.op === op ? { borderColor: "#22d3ee", color: "#22d3ee" } : {}}
              >
                {op}
              </button>
            ))}
          </div>
        </div>
        <div className="ib-child-slot">
          <span className="ib-child-label">LEFT</span>
          <div className="ib-child-indent">
            <NodeEditor node={node.left}  onChange={left  => onChange({ ...node, left  })} depth={depth + 1} />
          </div>
        </div>
        <div className="ib-child-slot">
          <span className="ib-child-label">RIGHT</span>
          <div className="ib-child-indent">
            <NodeEditor node={node.right} onChange={right => onChange({ ...node, right })} depth={depth + 1} />
          </div>
        </div>
      </>
    );
  }

  // ── Unary op ──
  if (node.node === "unop") {
    body = (
      <>
        <div className="ib-field-row">
          <span className="ib-field-label">Function</span>
          <div className="ib-op-pill">
            {UNARY_OPS.map(op => (
              <button
                key={op}
                className="ib-btn-sm"
                onClick={() => onChange({ ...node, op })}
                style={node.op === op ? { borderColor: "#22d3ee", color: "#22d3ee" } : {}}
              >
                {op}
              </button>
            ))}
          </div>
        </div>
        <div className="ib-child-slot">
          <span className="ib-child-label">INPUT</span>
          <div className="ib-child-indent">
            <NodeEditor node={node.operand} onChange={operand => onChange({ ...node, operand })} depth={depth + 1} />
          </div>
        </div>
      </>
    );
  }

  // ── Clamp ──
  if (node.node === "clamp") {
    body = (
      <>
        {[["value","VALUE"],["lo","MIN"],["hi","MAX"]].map(([key, label]) => (
          <div className="ib-child-slot" key={key}>
            <span className="ib-child-label">{label}</span>
            <div className="ib-child-indent">
              <NodeEditor node={node[key]} onChange={v => onChange({ ...node, [key]: v })} depth={depth + 1} />
            </div>
          </div>
        ))}
      </>
    );
  }

  // ── If/else ──
  if (node.node === "ifelse") {
    body = (
      <>
        <div className="ib-field-row" style={{ gap: "0.4rem", flexWrap: "wrap" }}>
          <span className="ib-field-label">Condition</span>
          <div className="ib-child-indent" style={{ flex: 1 }}>
            <NodeEditor node={node.cond_left}  onChange={v => onChange({ ...node, cond_left: v })}  depth={depth + 1} />
          </div>
          <select className="ib-op-select" value={node.cond_op} onChange={e => onChange({ ...node, cond_op: e.target.value })}>
            {COND_OPS.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
          <div className="ib-child-indent" style={{ flex: 1 }}>
            <NodeEditor node={node.cond_right} onChange={v => onChange({ ...node, cond_right: v })} depth={depth + 1} />
          </div>
        </div>
        {[["then","THEN"],["else_","ELSE"]].map(([key, label]) => (
          <div className="ib-child-slot" key={key}>
            <span className="ib-child-label">{label}</span>
            <div className="ib-child-indent">
              <NodeEditor node={node[key]} onChange={v => onChange({ ...node, [key]: v })} depth={depth + 1} />
            </div>
          </div>
        ))}
      </>
    );
  }

  return (
    <div className="ib-node" style={indent ? { marginTop: 4 } : {}}>
      {header}
      <div className="ib-node-body">{body}</div>
    </div>
  );
}

// ─── Indicator editor card ────────────────────────────────────────────────────

function IndicatorEditor({ indicator, onChange, onDelete }) {
  const [showJson, setShowJson] = useState(false);
  const [copied, setCopied]     = useState(false);

  const serialised = serialiseNode(indicator.expr);
  const json = JSON.stringify({ name: indicator.name, color: indicator.color, description: indicator.description, expr: serialised }, null, 2);

  return (
    <div className="ib-new-card">
      <div className="ib-new-header">
        <input
          className="ib-new-name-input"
          value={indicator.name}
          onChange={e => onChange({ ...indicator, name: e.target.value })}
          placeholder="indicator_name"
          spellCheck={false}
        />
        <div className="ib-color-row">
          {PALETTE.map(c => (
            <div
              key={c}
              className={`ib-color-swatch${indicator.color === c ? " selected" : ""}`}
              style={{ background: c }}
              onClick={() => onChange({ ...indicator, color: c })}
              title={c}
            />
          ))}
        </div>
        <button className="ib-btn-sm" onClick={() => setShowJson(s => !s)} style={{ fontSize: "0.75rem" }}>
          {showJson ? "Hide JSON" : "JSON"}
        </button>
        <button className="ib-remove-ind" onClick={onDelete}>Remove</button>
      </div>

      <div style={{ padding: "0.6rem 1.25rem", borderBottom: "1px solid #1f2937", background: "#0b1120" }}>
        <input
          className="ib-desc-input"
          value={indicator.description}
          onChange={e => onChange({ ...indicator, description: e.target.value })}
          placeholder="Description (optional)"
        />
      </div>

      {showJson && (
        <div className="ib-json-panel" style={{ margin: "0.75rem 1.25rem 0", borderRadius: 10 }}>
          <div className="ib-json-label">Expression JSON</div>
          <pre className="ib-json-pre">{json}</pre>
          <button
            className="ib-btn-sm ib-json-copy"
            onClick={() => navigator.clipboard.writeText(json).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })}
          >
            {copied ? "✓" : "Copy"}
          </button>
        </div>
      )}

      <div className="ib-expr-section">
        <div className="ib-section-label">Expression</div>
        <div className="ib-expr-preview">{describeNode(indicator.expr)}</div>
        <NodeEditor
          node={indicator.expr}
          onChange={expr => onChange({ ...indicator, expr })}
        />
      </div>
    </div>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────

let _indId = 1;
const indUid = () => String(_indId++);

function defaultIndicator() {
  return {
    _id: indUid(),
    name: "my_indicator",
    description: "",
    color: "#22d3ee",
    expr: defaultNode(),
  };
}

export default function IndicatorBuilder() {
  const [indicators, setIndicators]     = useState([]);
  const [activeId, setActiveId]         = useState(null);
  const [loading, setLoading]           = useState(false);
  const [saving, setSaving]             = useState(false);
  const [error, setError]               = useState("");

  useEffect(() => {
    setLoading(true);
    fetch(`${API_BASE}/db/indicators`)
      .then(r => r.json())
      .then(d => {
        const loaded = (d.indicators || []).map(ind => ({
          _id: indUid(),
          name: ind.name,
          description: ind.description || "",
          color: ind.color || "#22d3ee",
          expr: inflateNode(ind.expr),
        }));
        setIndicators(loaded);
        if (loaded.length > 0) setActiveId(loaded[0]._id);
      })
      .catch(() => setError("Failed to load indicators"))
      .finally(() => setLoading(false));
  }, []);

  // Convert wire format back to internal format (add _id, flatten opType)
  function inflateNode(n) {
    if (!n) return makeConst(0);
    const id = indUid();
    if (n.node === "const")   return { _id: id, node: "const", value: n.value ?? 0 };
    if (n.node === "operand") {
      const { type: opType, ...params } = n.operand ?? {};
      return { _id: id, node: "operand", opType: opType ?? "price", ...params };
    }
    if (n.node === "binop")  return { _id: id, node: "binop",  op: n.op, left: inflateNode(n.left), right: inflateNode(n.right) };
    if (n.node === "unop")   return { _id: id, node: "unop",   op: n.op, operand: inflateNode(n.operand) };
    if (n.node === "clamp")  return { _id: id, node: "clamp",  value: inflateNode(n.value), lo: inflateNode(n.lo), hi: inflateNode(n.hi) };
    if (n.node === "ifelse") return { _id: id, node: "ifelse", cond_left: inflateNode(n.cond_left), cond_op: n.cond_op, cond_right: inflateNode(n.cond_right), then: inflateNode(n.then), else_: inflateNode(n.else_) };
    return makeConst(0);
  }

  const addIndicator = () => {
    const ind = defaultIndicator();
    setIndicators(prev => [...prev, ind]);
    setActiveId(ind._id);
  };

  const updateIndicator = (updated) => setIndicators(prev => prev.map(i => i._id === updated._id ? updated : i));

  const deleteIndicator = (id) => {
    const rest = indicators.filter(i => i._id !== id);
    setIndicators(rest);
    if (activeId === id) setActiveId(rest[0]?._id ?? null);
  };

  const validate = () => {
    for (const ind of indicators) {
      if (!ind.name.trim()) return "All indicators must have a name.";
      if (!/^[a-z_][a-z0-9_]*$/.test(ind.name)) return `"${ind.name}" must be snake_case (letters, numbers, underscores).`;
    }
    const names = indicators.map(i => i.name);
    if (new Set(names).size !== names.length) return "Indicator names must be unique.";
    return "";
  };

  const save = async () => {
    const err = validate();
    if (err) { setError(err); return; }
    setError("");
    setSaving(true);
    try {
      const payload = indicators.map(ind => ({
        name: ind.name,
        description: ind.description,
        color: ind.color,
        expr: serialiseNode(ind.expr),
      }));
      await fetch(`${API_BASE}/db/indicators`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ indicators: payload }),
      });
      alert('Indicators saved');
    } catch { setError('Failed to save indicators'); }
    finally { setSaving(false); }
  };

  const active = indicators.find(i => i._id === activeId);

  return (
    <>
      <style>{css}</style>
      <div className="view">
        <h2>Indicator Builder</h2>
        <p>Define reusable custom indicators as expression trees. Use them as operands in the Rule Builder.</p>

        <div className="ib-topbar" style={{ marginTop: "1.5rem" }}>
          <span style={{ fontSize: "0.8rem", color: "#6b7280" }}>{indicators.length} indicator{indicators.length !== 1 ? "s" : ""}</span>
          <div className="ib-topbar-sep" />
          <button className="ib-btn" onClick={addIndicator}>+ New Indicator</button>
          <button className="ib-btn-primary" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save All"}</button>
        </div>

        {error && <div className="ib-error" style={{ marginBottom: "1rem" }}>{error}</div>}

        {loading ? (
          <div className="ib-empty">Loading…</div>
        ) : (
          <div className="ib-wrap">
            {/* Sidebar */}
            <aside className="ib-sidebar">
              <div className="ib-sidebar-label">Indicators ({indicators.length})</div>
              {indicators.map(ind => (
                <div
                  key={ind._id}
                  className={`ib-ind-item${ind._id === activeId ? " active" : ""}`}
                  onClick={() => setActiveId(ind._id)}
                >
                  <span className="ib-ind-dot" style={{ background: ind.color }} />
                  <span className="ib-ind-name">{ind.name || "(unnamed)"}</span>
                  <button className="ib-ind-del" onClick={e => { e.stopPropagation(); deleteIndicator(ind._id); }} title="Delete">×</button>
                </div>
              ))}
              {indicators.length === 0 && (
                <div style={{ fontSize: "0.75rem", color: "#4b5563", padding: "0.5rem 0.25rem" }}>No indicators yet</div>
              )}

              <div className="ib-sidebar-label" style={{ marginTop: "0.75rem" }}>Node Types</div>
              {NODE_TYPES.map(t => (
                <div key={t.value} style={{ fontSize: "0.73rem", color: "#6b7280", padding: "0.15rem 0.1rem" }}>
                  <span style={{ fontFamily: "ui-monospace, monospace", color: "#22d3ee", marginRight: 5 }}>{t.value}</span>
                  {t.label.split("(")[0].trim()}
                </div>
              ))}
            </aside>

            {/* Editor */}
            <div className="ib-editor">
              {!active ? (
                <div className="ib-empty">
                  <div className="ib-empty-icon">◈</div>
                  Select an indicator or create a new one
                </div>
              ) : (
                <IndicatorEditor
                  key={active._id}
                  indicator={active}
                  onChange={updateIndicator}
                  onDelete={() => deleteIndicator(active._id)}
                />
              )}
            </div>
          </div>
        )}
      </div>
    </>
  );
}