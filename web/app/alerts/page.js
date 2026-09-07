import Alerts from "../components/Alerts";
import { getAll } from "../lib/data";

export const metadata = { title: "Alerts · Pra River Watch" };

export default function Page() {
  const { alerts, stations } = getAll();
  return <Alerts alerts={alerts} stations={stations} />;
}
