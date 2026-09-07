export const metadata = {
  title: "Pra River Early Warning",
  description: "Satellite turbidity monitoring for the Pra River, Ghana",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui, sans-serif", margin: 0 }}>{children}</body>
    </html>
  );
}
