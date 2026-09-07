import LiveMap from "../components/LiveMap";
import { getAll } from "../lib/data";

export const metadata = { title: "Live Map · Pra River Watch" };

export default function Page() {
  const { stations, series, river, network, candidates } = getAll();
  return <LiveMap stations={stations} series={series} river={river}
                  network={network} candidates={candidates} />;
}
