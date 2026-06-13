import { useEffect, useRef, useState } from "react";

export function useElementWidth<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [width, setWidth] = useState<number | undefined>();

  useEffect(() => {
    const element = ref.current;
    if (!element) return;

    const update = () => setWidth(Math.round(element.getBoundingClientRect().width));
    update();

    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", update);
      return () => window.removeEventListener("resize", update);
    }

    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return [ref, width] as const;
}
