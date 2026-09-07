import Overview from "./components/Overview";
import { getAll } from "./lib/data";

export default function Page() {
  const { summary, stations, series, alerts, river } = getAll();
  return <Overview summary={summary} stations={stations} series={series}
                   alerts={alerts} river={river} />;
}
