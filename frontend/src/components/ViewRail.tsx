import { Fragment } from "react";
import { VIEWS, type AppView } from "../lib/views";

// Left-hand view switcher, data-driven from VIEWS. The first "lab" entry gets a
// small group label so the exploration tools read as a secondary workbench under
// the Normals headline, not as peers of it. Disabled entries still render — the
// roadmap stays visible — but aren't clickable until their gate passes.
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
        const startsLab = view.group === "lab" && VIEWS[index - 1]?.group !== "lab";
        return (
          <Fragment key={view.id}>
            {startsLab && (
              <p className="view-rail-group" aria-hidden>
                Lab
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
