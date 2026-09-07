const POINTS = [
  { id: "control", name: "Pra Upstream (Control)", role: "control" },
  { id: "monitor", name: "Pra at Dunkwa", role: "monitor" },
  { id: "intake", name: "Daboase Intake (GWCL)", role: "intake" },
];

export default function Home() {
  return (
    <main style={{ maxWidth: 720, margin: "0 auto", padding: 32 }}>
      <h1 style={{ marginBottom: 4 }}>Pra River Early Warning</h1>
      <p style={{ color: "#555", marginTop: 0 }}>
        Satellite turbidity monitoring — placeholder deploy (STEP 0 check 5).
      </p>
      <ul style={{ padding: 0, listStyle: "none" }}>
        {POINTS.map((p) => (
          <li
            key={p.id}
            style={{
              border: "1px solid #ddd",
              borderRadius: 8,
              padding: 16,
              marginBottom: 12,
            }}
          >
            <strong>{p.name}</strong>
            <div style={{ color: "#777", fontSize: 14 }}>
              {p.role} — awaiting first reading
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
