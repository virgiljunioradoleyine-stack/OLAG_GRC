import "./globals.css";

export const metadata = {
  title: "Pra River Early Warning",
  description:
    "Satellite turbidity monitoring and anomaly detection for the Pra River, Ghana",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
