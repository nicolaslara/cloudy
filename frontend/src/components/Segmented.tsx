// Generic single-select pill group (resolution, radius, scale, …). Controlled —
// holds no state of its own — and uses aria-pressed buttons rather than radios so
// it reads as a toolbar toggle. `format` keeps option values (e.g. 10, "auto")
// decoupled from their display labels.
export function Segmented<T extends string | number>({
  label,
  options,
  value,
  onChange,
  format,
  disabled,
}: {
  label: string;
  options: T[];
  value: T;
  onChange: (next: T) => void;
  format: (option: T) => string;
  disabled?: boolean;
}) {
  const controlId = `segmented-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;

  return (
    <div className="segmented-control">
      <span className="segmented-label" id={controlId}>
        {label}
      </span>
      <div className="segmented" role="group" aria-labelledby={controlId}>
        {options.map((option) => (
          <button
            key={option}
            type="button"
            aria-pressed={option === value}
            className={option === value ? "active" : undefined}
            disabled={disabled}
            onClick={() => onChange(option)}
          >
            {format(option)}
          </button>
        ))}
      </div>
    </div>
  );
}
