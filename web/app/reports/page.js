import Reports from "../components/Reports";
import { getAll } from "../lib/data";

export const metadata = { title: "Reports · Pra River Watch" };

export default function Page() {
  const { summary, stations, series, alerts } = getAll();
  return <Reports summary={summary} stations={stations} series={series} alerts={alerts} />;
}
