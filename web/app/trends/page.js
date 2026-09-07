import Trends from "../components/Trends";
import { getAll } from "../lib/data";

export const metadata = { title: "Data & Trends · Pra River Watch" };

export default function Page() {
  const { stations, series } = getAll();
  return <Trends stations={stations} series={series} />;
}
