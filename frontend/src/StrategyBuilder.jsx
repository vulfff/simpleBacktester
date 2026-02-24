import { useState, useRef, useCallback } from "react";

// ─── Schema ──────────────────────────────────────────────────────────────────
// NOTE on "constant": the frontend stores the param as "value" (not "value_").
// ConstantOperand.to_dict() / _from_dict uses the key "value", so that is what
// we must serialise. The Python dataclass internal field is named value_ only
// to avoid shadowing the built-in, but the wire format is always "value".
const OPERAND_SCHEMA = {
  constant:  { label: "Constant",   color: "#6b7280", params: [{ name: "value",      type: "number",  label: "Value",      default: 0 }] },
  price:     { label: "Price",      color: "#22d3ee", params: [{ name: "field",      type: "select",  label: "Field",      default: "mid",   options: ["bid","ask","mid","volume"] }] },
  lookback:  { label: "N bars ago", color: "#f59e0b", params: [{ name: "field",      type: "select",  label: "Field",      default: "mid",   options: ["bid","ask","mid","volume"] },
                                                                 { name: "period",    type: "integer", label: "Bars ago",   default: 1,      min: 1 }] },
  sma:       { label: "SMA",        color: "#34d399", params: [{ name: "field",      type: "select",  label: "Field",      default: "mid",   options: ["bid","ask","mid","volume"] },
                                                                 { name: "period",    type: "integer", label: "Period",     default: 20,     min: 2 }] },
  ema:       { label: "EMA",        color: "#38bdf8", params: [{ name: "field",      type: "select",  label: "Field",      default: "mid",   options: ["bid","ask","mid","volume"] },
                                                                 { name: "period",    type: "integer", label: "Period",     default: 20,     min: 2 }] },
  rsi:       { label: "RSI",        color: "#a78bfa", params: [{ name: "field",      type: "select",  label: "Field",      default: "mid",   options: ["bid","ask","mid","volume"] },
                                                                 { name: "period",    type: "integer", label: "Period",     default: 14,     min: 2 }] },
  bollinger: { label: "Bollinger",  color: "#f472b6", params: [{ name: "field",      type: "select",  label: "Field",      default: "mid",   options: ["bid","ask","mid","volume"] },
                                                                 { name: "period",    type: "integer", label: "Period",     default: 20,     min: 2 },
                                                                 { name: "std_dev",   type: "number",  label: "Std Dev",    default: 2 },
                                                                 { name: "component", type: "select",  label: "Band",       default: "upper", options: ["upper","middle","lower","width","pct_b"] }] },
  macd:      { label: "MACD",       color: "#fb923c", params: [{ name: "fast",       type: "integer", label: "Fast",       default: 12,     min: 1 },
                                                                 { name: "slow",       type: "integer", label: "Slow",       default: 26,     min: 1 },
                                                                 { name: "signal",     type: "integer", label: "Signal",     default: 9,      min: 1 },
                                                                 { name: "component",  type: "select",  label: "Output",     default: "macd",  options: ["macd","signal","hist"] }] },
  // "custom" type added dynamically when indicators are loaded – see buildCustomSchema()
};

// Call this once custom indicators are loaded from the API to extend OPERAND_SCHEMA
export function buildCustomSchema(indicators) {
  indicators.forEach(ind => {
    OPERAND_SCHEMA[`custom:${ind.name}`] = {
      label: ind.name,
      color: ind.color || "#22d3ee",
      isCustom: true,
      indicatorName: ind.name,
      params: [],
    };
  });
}

// When serialising a custom operand, collapse custom:name → {type:"custom", name}
function serialiseOperand(operand) {
  const { _id, type, ...rest } = operand;
  if (type.startsWith("custom:")) {
    return { type: "custom", name: type.slice(7) };
  }
  return { type, ...rest };
}

const OPERATORS = [
  { value: ">",           label: ">" },
  { value: ">=",          label: "≥" },
  { value: "<",           label: "<" },
  { value: "<=",          label: "≤" },
  { value: "==",          label: "=" },
  { value: "!=",          label: "≠" },
  { value: "cross_above", label: "↗ crosses above" },
  { value: "cross_below", label: "↘ crosses below" },
];

const ROLES = [
  { value: "entry_long",  label: "Enter Long",  color: "#34d399", bg: "rgba(52,211,153,0.12)",  border: "rgba(52,211,153,0.3)"  },
  { value: "exit_long",   label: "Exit Long",   color: "#f87171", bg: "rgba(248,113,113,0.12)", border: "rgba(248,113,113,0.3)" },
  { value: "entry_short", label: "Enter Short", color: "#fb923c", bg: "rgba(251,146,60,0.12)",  border: "rgba(251,146,60,0.3)"  },
  { value: "exit_short",  label: "Exit Short",  color: "#a78bfa", bg: "rgba(167,139,250,0.12)", border: "rgba(167,139,250,0.3)" },
];

const TIMINGS = [
  { value: "on_change",  label: "On Signal Change" },
  { value: "every_tick", label: "Every Tick" },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────
let _id = 1;
const uid = () => String(_id++);

function defaultOperand(type = "price") {
  const schema = OPERAND_SCHEMA[type];
  const params = {};
  (schema?.params ?? []).forEach(p => { params[p.name] = p.default; });
  return { _id: uid(), type, ...params };
}

function defaultCondition() {
  return { _id: uid(), left: defaultOperand("price"), operator: ">", right: defaultOperand("constant") };
}

function defaultRule() {
  return { _id: uid(), name: "New Rule", role: "entry_long", conditions: [defaultCondition()], combiner: "and", timing: "on_change", quantity: 1 };
}

// Serialise the full ruleset to the wire format the backend expects
export function ruleSetToJson(name, rules) {
  return {
    name,
    rules: rules.map(({ _id, ...r }) => ({
      ...r,
      conditions: r.conditions.map(({ _id, left, right, ...c }) => ({
        ...c,
        left:  serialiseOperand(left),
        right: serialiseOperand(right),
      })),
    })),
  };
}

// ─── Scoped styles ────────────────────────────────────────────────────────────
const css = `
  .rb-wrap { display: flex; gap: 1rem; align-items: flex-start; }

  .rb-sidebar {
    flex-shrink: 0; width: 200px;
    background: #0f172a; border: 1px solid #1f2937; border-radius: 16px;
    padding: 1rem; display: flex; flex-direction: column; gap: 0.5rem;
    position: sticky; top: 0;
  }
  .rb-sidebar-label {
    font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
    color: #6b7280; padding-bottom: 0.25rem; border-bottom: 1px solid #1f2937; margin-bottom: 0.25rem;
  }
  .rb-rule-item {
    display: flex; align-items: center; gap: 8px; padding: 0.45rem 0.6rem;
    border-radius: 8px; cursor: pointer; transition: background 0.15s;
    font-size: 0.8rem; color: #9ca3af;
  }
  .rb-rule-item:hover  { background: #1f2937; color: #e5e7eb; }
  .rb-rule-item.active { background: rgba(34,211,238,0.1); color: #22d3ee; }
  .rb-rule-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
  .rb-rule-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .rb-rule-badge { font-size: 0.65rem; color: #4b5563; font-variant-numeric: tabular-nums; }
  .rb-legend-item { display: flex; align-items: center; gap: 7px; padding: 0.2rem 0.1rem; font-size: 0.75rem; color: #6b7280; }

  .rb-editor { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1rem; }

  .rb-rule-card {
    background: #111827; border: 1px solid #1f2937; border-radius: 16px;
    overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.2);
  }
  .rb-rule-header {
    display: flex; align-items: center; gap: 0.75rem; padding: 0.9rem 1.25rem;
    background: #0f172a; border-bottom: 1px solid #1f2937; flex-wrap: wrap;
  }
  .rb-rule-name-input {
    flex: 1; min-width: 120px; background: transparent; border: none;
    color: #e5e7eb; font-family: inherit; font-size: 0.95rem; font-weight: 600; outline: none;
  }
  .rb-rule-name-input:focus { color: #22d3ee; }
  .rb-role-badge {
    display: inline-flex; align-items: center; padding: 0.25rem 0.75rem;
    border-radius: 999px; font-size: 0.75rem; font-weight: 600; cursor: pointer;
    transition: opacity 0.15s; white-space: nowrap; border: 1px solid;
  }
  .rb-role-badge:hover { opacity: 0.75; }

  .rb-rule-meta {
    display: flex; align-items: center; gap: 1.5rem; padding: 0.7rem 1.25rem;
    border-bottom: 1px solid #1f2937; flex-wrap: wrap; background: #0b1120;
  }
  .rb-meta-group { display: flex; align-items: center; gap: 0.5rem; }
  .rb-meta-label { font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: #6b7280; }
  .rb-meta-group select, .rb-meta-group input[type=number] {
    background: #111827; border: 1px solid #334155; border-radius: 8px;
    padding: 0.3rem 0.55rem; color: #e5e7eb; font-family: inherit; font-size: 0.8rem;
    outline: none; transition: border-color 0.15s;
  }
  .rb-meta-group select:focus, .rb-meta-group input:focus { border-color: #22d3ee; }
  .rb-meta-group input[type=number] { width: 72px; }
  .rb-combiner-btn {
    background: #1e293b; border: 1px solid #334155; border-radius: 6px;
    color: #22d3ee; font-family: inherit; font-size: 0.7rem; font-weight: 700;
    letter-spacing: 0.08em; padding: 0.25rem 0.6rem; cursor: pointer;
    transition: background 0.15s, border-color 0.15s;
  }
  .rb-combiner-btn:hover { background: #334155; border-color: #22d3ee; }

  .rb-conditions { padding: 1rem 1.25rem; display: flex; flex-direction: column; gap: 0.5rem; }
  .rb-combiner-divider { display: flex; align-items: center; gap: 8px; padding: 0.1rem 0; }
  .rb-combiner-divider-line { height: 1px; flex: 1; background: #1f2937; }
  .rb-combiner-pill {
    font-size: 0.65rem; font-weight: 700; letter-spacing: 0.12em; padding: 0.15rem 0.55rem;
    border-radius: 999px; background: rgba(34,211,238,0.08); color: #22d3ee;
    border: 1px solid rgba(34,211,238,0.2);
  }

  .rb-cond-row {
    display: flex; align-items: stretch; background: #0b1120;
    border: 1px solid #1e293b; border-radius: 10px; overflow: hidden; transition: border-color 0.15s;
  }
  .rb-cond-row:hover { border-color: #334155; }
  .rb-cond-row.drag-over { border-color: #22d3ee; box-shadow: 0 0 0 1px #22d3ee; }
  .rb-cond-row.dragging  { opacity: 0.45; }

  .rb-drag-handle {
    display: flex; align-items: center; padding: 0 10px; cursor: grab; color: #374151;
    font-size: 13px; border-right: 1px solid #1e293b; background: #0f172a; user-select: none; transition: color 0.15s;
  }
  .rb-drag-handle:hover { color: #6b7280; }
  .rb-drag-handle:active { cursor: grabbing; }

  .rb-operand { flex: 1; display: flex; flex-direction: column; gap: 6px; padding: 0.65rem 0.9rem; min-width: 0; }
  .rb-operand-top { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .rb-operand-tag {
    font-size: 0.65rem; font-weight: 700; letter-spacing: 0.07em; text-transform: uppercase;
    padding: 0.15rem 0.55rem; border-radius: 5px; white-space: nowrap;
  }
  .rb-operand-top select {
    background: #111827; border: 1px solid #1e293b; border-radius: 6px; padding: 0.2rem 0.45rem;
    color: #9ca3af; font-family: inherit; font-size: 0.75rem; outline: none; cursor: pointer; transition: border-color 0.15s, color 0.15s;
  }
  .rb-operand-top select:focus, .rb-operand-top select:hover { border-color: #334155; color: #e5e7eb; }
  .rb-operand-params { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .rb-param-group { display: flex; align-items: center; gap: 4px; }
  .rb-param-label { font-size: 0.7rem; color: #6b7280; white-space: nowrap; }
  .rb-param-group select, .rb-param-group input[type=number] {
    background: #111827; border: 1px solid #1e293b; border-radius: 6px;
    padding: 0.2rem 0.45rem; color: #e5e7eb; font-family: inherit; font-size: 0.75rem;
    outline: none; transition: border-color 0.15s;
  }
  .rb-param-group select:focus, .rb-param-group input:focus { border-color: #22d3ee; }
  .rb-param-group input[type=number] { width: 62px; }

  .rb-operator-block {
    display: flex; align-items: center; padding: 0 0.75rem;
    background: #0f172a; border-left: 1px solid #1e293b; border-right: 1px solid #1e293b; flex-shrink: 0;
  }
  .rb-operator-block select {
    background: transparent; border: none; color: #22d3ee; font-family: inherit;
    font-size: 0.85rem; font-weight: 600; outline: none; cursor: pointer; min-width: 80px; text-align: center;
  }

  .rb-cond-del {
    display: flex; align-items: center; padding: 0 10px; background: transparent;
    border: none; border-left: 1px solid #1e293b; color: #4b5563; cursor: pointer; font-size: 1rem; transition: color 0.15s, background 0.15s;
  }
  .rb-cond-del:hover { color: #f87171; background: rgba(248,113,113,0.08); }

  .rb-add-cond {
    background: transparent; border: 1px dashed #1e293b; border-radius: 8px;
    padding: 0.45rem 1rem; color: #4b5563; font-family: inherit; font-size: 0.8rem;
    cursor: pointer; transition: border-color 0.15s, color 0.15s; align-self: flex-start; margin-top: 0.25rem;
  }
  .rb-add-cond:hover { border-color: #22d3ee; color: #22d3ee; }

  .rb-json-panel {
    background: #0b1120; border: 1px dashed #334155; border-radius: 12px;
    padding: 1rem 1.25rem; position: relative;
  }
  .rb-json-label { font-size: 0.7rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: #6b7280; margin-bottom: 0.5rem; }
  .rb-json-pre {
    font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 0.75rem; color: #93c5fd;
    white-space: pre; overflow-x: auto; max-height: 180px; overflow-y: auto; line-height: 1.6;
  }
  .rb-json-copy { position: absolute; top: 0.75rem; right: 0.75rem; }

  .rb-topbar { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .rb-topbar-title { font-size: 0.8rem; color: #6b7280; }
  .rb-topbar-name {
    background: #0f172a; border: 1px solid #334155; border-radius: 8px;
    padding: 0.35rem 0.7rem; color: #e5e7eb; font-family: inherit; font-size: 0.9rem;
    font-weight: 600; outline: none; min-width: 180px; transition: border-color 0.15s;
  }
  .rb-topbar-name:focus { border-color: #22d3ee; }
  .rb-topbar-sep { flex: 1; }

  .rb-btn {
    background: #1e293b; border: 1px solid #334155; border-radius: 10px;
    padding: 0.45rem 1rem; color: #e5e7eb; font-family: inherit; font-size: 0.85rem;
    cursor: pointer; transition: border-color 0.15s, color 0.15s;
  }
  .rb-btn:hover { border-color: #22d3ee; color: #22d3ee; }
  .rb-btn-primary {
    background: linear-gradient(135deg, #6366f1, #22d3ee); border: none; border-radius: 999px;
    padding: 0.5rem 1.4rem; color: #0f172a; font-family: inherit; font-size: 0.85rem;
    font-weight: 600; cursor: pointer; transition: transform 0.15s, opacity 0.15s;
  }
  .rb-btn-primary:hover { transform: translateY(-1px); opacity: 0.9; }
  .rb-remove-rule {
    background: transparent; border: 1px solid rgba(248,113,113,0.3); border-radius: 6px;
    padding: 0.25rem 0.65rem; color: #f87171; font-family: inherit; font-size: 0.75rem;
    cursor: pointer; transition: background 0.15s;
  }
  .rb-remove-rule:hover { background: rgba(248,113,113,0.12); }

  .rb-empty { text-align: center; padding: 3rem 1rem; color: #4b5563; font-size: 0.9rem; }
  .rb-empty-icon { font-size: 2rem; margin-bottom: 0.75rem; opacity: 0.4; }

  /* optgroup styling for custom indicators in the operand select */
  .rb-operand-top select optgroup { color: #6b7280; font-size: 0.7rem; }
  .rb-operand-top select option  { color: #e5e7eb; }
`;

// ─── Components ──────────────────────────────────────────────────────────────

function OperandEditor({ operand, onChange, customIndicators = [] }) {
  const schema = OPERAND_SCHEMA[operand.type];
  const c = schema?.color ?? "#6b7280";

  const handleTypeChange = (newType) => {
    const s = OPERAND_SCHEMA[newType];
    const p = {};
    (s?.params ?? []).forEach(x => { p[x.name] = x.default; });
    onChange({ _id: operand._id, type: newType, ...p });
  };

  return (
    <div className="rb-operand">
      <div className="rb-operand-top">
        <span
          className="rb-operand-tag"
          style={{ background: c + "1a", color: c, border: `1px solid ${c}40` }}
        >
          {schema?.label ?? operand.type}
        </span>
        <select value={operand.type} onChange={e => handleTypeChange(e.target.value)}>
          <optgroup label="Primitives">
            {["constant","price","lookback"].map(k => (
              <option key={k} value={k}>{OPERAND_SCHEMA[k].label}</option>
            ))}
          </optgroup>
          <optgroup label="Indicators">
            {["sma","ema","rsi","bollinger","macd"].map(k => (
              <option key={k} value={k}>{OPERAND_SCHEMA[k].label}</option>
            ))}
          </optgroup>
          {customIndicators.length > 0 && (
            <optgroup label="Custom">
              {customIndicators.map(ind => (
                <option key={`custom:${ind.name}`} value={`custom:${ind.name}`}>{ind.name}</option>
              ))}
            </optgroup>
          )}
        </select>
      </div>
      {schema && schema.params.length > 0 && (
        <div className="rb-operand-params">
          {schema.params.map(p => (
            <div className="rb-param-group" key={p.name}>
              <span className="rb-param-label">{p.label}</span>
              {p.type === "select" ? (
                <select
                  value={operand[p.name] ?? p.default}
                  onChange={e => onChange({ ...operand, [p.name]: e.target.value })}
                >
                  {p.options.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              ) : (
                <input
                  type="number"
                  value={operand[p.name] ?? p.default}
                  min={p.min}
                  step={p.type === "integer" ? 1 : 0.01}
                  onChange={e => onChange({ ...operand, [p.name]: p.type === "integer" ? parseInt(e.target.value) : parseFloat(e.target.value) })}
                />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ConditionRow({ condition, onChange, onDelete, onDragStart, onDragEnter, onDragEnd, isDragging, isDropTarget, customIndicators }) {
  return (
    <div
      className={`rb-cond-row${isDragging ? " dragging" : ""}${isDropTarget ? " drag-over" : ""}`}
      draggable
      onDragStart={onDragStart}
      onDragEnter={onDragEnter}
      onDragEnd={onDragEnd}
      onDragOver={e => e.preventDefault()}
    >
      <div className="rb-drag-handle" title="Drag to reorder">⠿</div>
      <OperandEditor operand={condition.left}  onChange={left  => onChange({ ...condition, left  })} customIndicators={customIndicators} />
      <div className="rb-operator-block">
        <select value={condition.operator} onChange={e => onChange({ ...condition, operator: e.target.value })}>
          {OPERATORS.map(op => <option key={op.value} value={op.value}>{op.label}</option>)}
        </select>
      </div>
      <OperandEditor operand={condition.right} onChange={right => onChange({ ...condition, right })} customIndicators={customIndicators} />
      <button className="rb-cond-del" onClick={onDelete} title="Remove">×</button>
    </div>
  );
}

function RuleEditor({ rule, onChange, onDelete, customIndicators }) {
  const role = ROLES.find(r => r.value === rule.role);
  const dragRef = useRef(null);
  const [dragOver, setDragOver] = useState(null);

  const updateCond = (id, u) => onChange({ ...rule, conditions: rule.conditions.map(c => c._id === id ? u : c) });
  const deleteCond = id => rule.conditions.length > 1 && onChange({ ...rule, conditions: rule.conditions.filter(c => c._id !== id) });
  const addCond    = ()  => onChange({ ...rule, conditions: [...rule.conditions, defaultCondition()] });

  const cycleRole = () => {
    const idx = ROLES.findIndex(r => r.value === rule.role);
    onChange({ ...rule, role: ROLES[(idx + 1) % ROLES.length].value });
  };

  const handleDragEnd = () => {
    if (dragRef.current !== null && dragOver !== null && dragRef.current !== dragOver) {
      const conds = [...rule.conditions];
      const [moved] = conds.splice(dragRef.current, 1);
      conds.splice(dragOver, 0, moved);
      onChange({ ...rule, conditions: conds });
    }
    dragRef.current = null;
    setDragOver(null);
  };

  return (
    <div className="rb-rule-card">
      <div className="rb-rule-header">
        <span
          className="rb-role-badge"
          style={{ color: role.color, background: role.bg, borderColor: role.border }}
          onClick={cycleRole}
          title="Click to cycle role"
        >
          {role.label}
        </span>
        <input className="rb-rule-name-input" value={rule.name} onChange={e => onChange({ ...rule, name: e.target.value })} spellCheck={false} />
        <button className="rb-remove-rule" onClick={onDelete}>Remove</button>
      </div>
      <div className="rb-rule-meta">
        <div className="rb-meta-group">
          <span className="rb-meta-label">Role</span>
          <select value={rule.role} onChange={e => onChange({ ...rule, role: e.target.value })}>
            {ROLES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
          </select>
        </div>
        <div className="rb-meta-group">
          <span className="rb-meta-label">Match</span>
          <button className="rb-combiner-btn" onClick={() => onChange({ ...rule, combiner: rule.combiner === "and" ? "or" : "and" })}>
            {rule.combiner.toUpperCase()}
          </button>
          <span style={{ fontSize: "0.7rem", color: "#4b5563" }}>
            {rule.combiner === "and" ? "all conditions" : "any condition"}
          </span>
        </div>
        <div className="rb-meta-group">
          <span className="rb-meta-label">Fire</span>
          <select value={rule.timing} onChange={e => onChange({ ...rule, timing: e.target.value })}>
            {TIMINGS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>
        <div className="rb-meta-group">
          <span className="rb-meta-label">Qty</span>
          <input
            type="number" value={rule.quantity} min={0.01} step={0.01}
            onChange={e => onChange({ ...rule, quantity: parseFloat(e.target.value) || 1 })}
          />
        </div>
      </div>
      <div className="rb-conditions">
        {rule.conditions.map((cond, idx) => (
          <div key={cond._id}>
            {idx > 0 && (
              <div className="rb-combiner-divider">
                <div className="rb-combiner-divider-line" />
                <span className="rb-combiner-pill">{rule.combiner.toUpperCase()}</span>
                <div className="rb-combiner-divider-line" />
              </div>
            )}
            <ConditionRow
              condition={cond}
              onChange={u => updateCond(cond._id, u)}
              onDelete={() => deleteCond(cond._id)}
              onDragStart={() => { dragRef.current = idx; }}
              onDragEnter={() => setDragOver(idx)}
              onDragEnd={handleDragEnd}
              isDragging={dragRef.current === idx}
              isDropTarget={dragOver === idx && dragRef.current !== idx}
              customIndicators={customIndicators}
            />
          </div>
        ))}
        <button className="rb-add-cond" onClick={addCond}>+ Add Condition</button>
      </div>
    </div>
  );
}

// ─── Main export ──────────────────────────────────────────────────────────────
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000';

export default function StrategyRuleBuilder() {
  const [ruleSetName, setRuleSetName]   = useState("My Strategy");
  const [rules, setRules]               = useState([defaultRule()]);
  const [activeRuleId, setActiveRuleId] = useState(rules[0]._id);
  const [showJson, setShowJson]         = useState(false);
  const [copied, setCopied]             = useState(false);
  const [saving, setSaving]             = useState(false);
  // Custom indicators for the operand picker
  const [customIndicators, setCustomIndicators] = useState([]);

  // Load custom indicators so they appear in the operand selector
  useState(() => {
    fetch(`${API_BASE}/db/indicators`)
      .then(r => r.json())
      .then(d => setCustomIndicators(d.indicators || []))
      .catch(() => {});
  }, []);

  const addRule = () => {
    const r = defaultRule();
    setRules(prev => [...prev, r]);
    setActiveRuleId(r._id);
  };

  const updateRule = useCallback(u => setRules(prev => prev.map(r => r._id === u._id ? u : r)), []);

  const deleteRule = id => {
    const rest = rules.filter(r => r._id !== id);
    setRules(rest);
    if (activeRuleId === id) setActiveRuleId(rest[0]?._id ?? null);
  };

  const payload = ruleSetToJson(ruleSetName, rules);
  const json = JSON.stringify(payload, null, 2);

  const save = async () => {
    setSaving(true);
    try {
      await fetch(`${API_BASE}/db/strategies`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategies: [{ name: ruleSetName, config: JSON.stringify({ rule_set: payload }) }] }),
      });
      alert('Strategy saved');
    } catch { alert('Failed to save'); }
    finally { setSaving(false); }
  };

  const copy = () => navigator.clipboard.writeText(json).then(() => {
    setCopied(true); setTimeout(() => setCopied(false), 1600);
  });

  const activeRule = rules.find(r => r._id === activeRuleId);

  return (
    <>
      <style>{css}</style>
      <div className="view">
        <h2>Rule Builder</h2>
        <p>Build signal rules — each rule targets a role (enter/exit long/short).</p>

        <div className="rb-topbar" style={{ marginTop: "1.5rem" }}>
          <span className="rb-topbar-title">Strategy name</span>
          <input className="rb-topbar-name" value={ruleSetName} onChange={e => setRuleSetName(e.target.value)} spellCheck={false} />
          <div className="rb-topbar-sep" />
          <button className="rb-btn" onClick={() => setShowJson(s => !s)}>{showJson ? "Hide JSON" : "View JSON"}</button>
          <button className="rb-btn-primary" onClick={save} disabled={saving}>{saving ? "Saving…" : "Save Strategy"}</button>
        </div>

        {showJson && (
          <div className="rb-json-panel" style={{ marginBottom: "1rem" }}>
            <div className="rb-json-label">Rule Set JSON</div>
            <pre className="rb-json-pre">{json}</pre>
            <button className="rb-btn rb-json-copy" style={{ fontSize: "0.75rem", padding: "0.3rem 0.7rem" }} onClick={copy}>
              {copied ? "✓ Copied" : "Copy"}
            </button>
          </div>
        )}

        <div className="rb-wrap">
          <aside className="rb-sidebar">
            <div className="rb-sidebar-label">Rules ({rules.length})</div>
            {rules.map(r => {
              const role = ROLES.find(ro => ro.value === r.role);
              return (
                <div
                  key={r._id}
                  className={`rb-rule-item${r._id === activeRuleId ? " active" : ""}`}
                  onClick={() => setActiveRuleId(r._id)}
                >
                  <span className="rb-rule-dot" style={{ background: role.color }} />
                  <span className="rb-rule-name">{r.name}</span>
                  <span className="rb-rule-badge">{r.conditions.length}c</span>
                </div>
              );
            })}
            <button className="rb-btn" style={{ width: "100%", marginTop: "0.25rem", fontSize: "0.8rem", padding: "0.4rem 0.75rem" }} onClick={addRule}>
              + New Rule
            </button>
            <div className="rb-sidebar-label" style={{ marginTop: "0.75rem" }}>Roles</div>
            {ROLES.map(r => (
              <div key={r.value} className="rb-legend-item">
                <span className="rb-rule-dot" style={{ background: r.color }} />
                {r.label}
              </div>
            ))}
          </aside>

          <div className="rb-editor">
            {!activeRule ? (
              <div className="rb-empty">
                <div className="rb-empty-icon">◇</div>
                Select a rule or create a new one
              </div>
            ) : (
              <RuleEditor key={activeRule._id} rule={activeRule} onChange={updateRule} onDelete={() => deleteRule(activeRule._id)} customIndicators={customIndicators} />
            )}
          </div>
        </div>
      </div>
    </>
  );
}