interface MultiselectOption {
  label: string;
  value: string;
  disabled?: boolean;
  disabledReason?: string;
}

interface MultiselectProps {
  label: string;
  options: MultiselectOption[];
  value: string[];
  onChange: (value: string[]) => void;
}

export function Multiselect({ label, options, value, onChange }: MultiselectProps) {
  function toggle(option: MultiselectOption) {
    if (option.disabled) {
      return;
    }
    const optionValue = option.value;
    if (value.includes(optionValue)) {
      onChange(value.filter((item) => item !== optionValue));
    } else {
      onChange([...value, optionValue]);
    }
  }

  return (
    <fieldset className="field-group">
      <legend>{label}</legend>
      {options.length > 0 ? (
        options.map((option) => (
          <label className="check-row" key={option.value}>
            <input
              aria-label={option.label}
              checked={value.includes(option.value)}
              disabled={option.disabled}
              type="checkbox"
              onChange={() => toggle(option)}
            />
            <span>{option.label}</span>
            {option.disabledReason ? <small>{option.disabledReason}</small> : null}
          </label>
        ))
      ) : (
        <span className="muted-text">暂无可选知识库</span>
      )}
    </fieldset>
  );
}
