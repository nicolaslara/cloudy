import { VIEWS, type AppView } from "../lib/views";

export function ViewRail({
  active,
  onChange,
}: {
  active: AppView;
  onChange: (view: AppView) => void;
}) {
  return (
    <nav className="view-rail" aria-label="Views">
      {VIEWS.map((view) => (
        <button
          key={view.id}
          type="button"
          className={active === view.id ? "active" : undefined}
          aria-current={active === view.id ? "page" : undefined}
          disabled={!view.enabled}
          onClick={() => view.enabled && onChange(view.id)}
        >
          {view.label}
          {!view.enabled && <span className="view-soon">soon</span>}
        </button>
      ))}
    </nav>
  );
}
