import "./globals.css";
import Nav from "./components/Nav";
import { getSummary } from "./lib/data";

export const metadata = {
  title: "Pra River Watch",
  description:
    "Satellite-derived early warning for unusual river and sediment conditions in the Pra basin, Ghana.",
};

export default function RootLayout({ children }) {
  const summary = getSummary();
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <Nav activeAlerts={summary?.active_alerts || 0} />
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
