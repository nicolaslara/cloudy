import { Fragment } from "react";
import { GROUP_LABELS, VIEWS, type AppView } from "../lib/views";

// Left-hand view switcher, data-driven from VIEWS. Each labelled group (Models,
// Lab) gets a small header before its first entry, so models and the exploration
// workbench read as distinct sections under the ungrouped product tabs. Disabled
// entries still render — the roadmap stays visible — but aren't clickable.
export function ViewRail({
  active,
  onChange,
}: {
  active: AppView;
  onChange: (view: AppView) => void;
}) {
  return (
    <nav className="view-rail" aria-label="Views">
      {VIEWS.map((view, index) => {
        const startsGroup = view.group != null && view.group !== VIEWS[index - 1]?.group;
        return (
          <Fragment key={view.id}>
            {startsGroup && view.group && (
              <p className="view-rail-group" aria-hidden>
                {GROUP_LABELS[view.group]}
              </p>
            )}
            <button
              type="button"
              className={active === view.id ? "active" : undefined}
              aria-current={active === view.id ? "page" : undefined}
              disabled={!view.enabled}
              onClick={() => view.enabled && onChange(view.id)}
            >
              {view.label}
              {!view.enabled && <span className="view-soon">soon</span>}
            </button>
          </Fragment>
        );
      })}
    </nav>
  );
}
