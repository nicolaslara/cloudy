import { useState } from "react";
import { useGeocode, type Candidate } from "../api/geocode";

interface SearchBoxProps {
  onSelect: (candidate: Candidate) => void;
}

// Address autocomplete with full keyboard combobox semantics. The debounce and
// network live in useGeocode; this component only owns the input text and the
// keyboard-highlight index. -1 means "nothing highlighted" (input itself focused),
// so Enter with -1 deliberately does nothing rather than picking a stale row.
export function SearchBox({ onSelect }: SearchBoxProps) {
  const [input, setInput] = useState("");
  const [highlighted, setHighlighted] = useState(-1);
  const { data: candidates, error } = useGeocode(input);

  const select = (candidate: Candidate) => {
    onSelect(candidate);
    setInput("");
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (!candidates || candidates.length === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setHighlighted((index) => Math.min(index + 1, candidates.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setHighlighted((index) => Math.max(index - 1, -1));
    } else if (event.key === "Enter" && highlighted >= 0) {
      event.preventDefault();
      const candidate = candidates[Math.min(highlighted, candidates.length - 1)];
      if (candidate) select(candidate);
    } else if (event.key === "Escape") {
      setInput("");
    }
  };

  const open = Boolean(candidates && candidates.length > 0);

  return (
    <section className="search">
      <input
        type="search"
        role="combobox"
        aria-expanded={open}
        aria-controls="address-suggestions"
        aria-activedescendant={highlighted >= 0 ? `suggestion-${highlighted}` : undefined}
        value={input}
        placeholder="Search a Swedish address…"
        aria-label="Address search"
        onChange={(event) => {
          setInput(event.target.value);
          setHighlighted(-1); // new query → stale highlight index
        }}
        onKeyDown={onKeyDown}
      />
      {error && <p className="search-note">Address search is unavailable right now.</p>}
      {open && candidates && (
        <ul className="suggestions" id="address-suggestions" role="listbox">
          {candidates.map((candidate, index) => (
            <li
              key={`${candidate.label}@${candidate.lat},${candidate.lon}`}
              id={`suggestion-${index}`}
              role="option"
              aria-selected={index === highlighted}
            >
              <button
                type="button"
                className={index === highlighted ? "highlighted" : undefined}
                onMouseEnter={() => setHighlighted(index)}
                onClick={() => select(candidate)}
              >
                {candidate.label}
              </button>
            </li>
          ))}
        </ul>
      )}
      {candidates && candidates.length === 0 && input.trim().length >= 3 && (
        <p className="search-note">No matches in Sweden.</p>
      )}
    </section>
  );
}
