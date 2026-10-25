/** The Streamlit dashboard (dashboard/app.py), inside the web app. It runs as its own server: on
 *  localhost at :8501, and on the Vultr VM on port 80 of the same host (deploy/vultr-dashboard.sh).
 *  VITE_DASHBOARD_URL overrides both. */
const dashboardUrl = (): string => {
  const set = import.meta.env.VITE_DASHBOARD_URL as string | undefined;
  if (set) return set;
  const { protocol, hostname } = window.location;
  return hostname === "localhost" || hostname === "127.0.0.1" ? `${protocol}//${hostname}:8501/` : `${protocol}//${hostname}/`;
};

export function Dashboard() {
  const url = dashboardUrl();
  return (
    <section className="dashboard" aria-label="Dashboard">
      <p className="dashboard__note caption">
        Blank? Start it with <code>python -m streamlit run app.py</code> in <code>dashboard/</code>, or{" "}
        <a href={url} target="_blank" rel="noreferrer">open it in its own tab</a>.
      </p>
      <iframe src={`${url}?embed=true&embed_options=dark_theme`} title="ClinicDrift dashboard" />
    </section>
  );
}
