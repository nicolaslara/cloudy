import { HealthCard } from "./components/HealthCard";

export function App() {
  return (
    <main className="page">
      <h1>cloudy</h1>
      <p className="tagline">Cloud cover and lightning history for Sweden.</p>
      <HealthCard />
    </main>
  );
}
