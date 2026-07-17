import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';

type GlanceStatus = {
  core: string;
  helper: string;
  tracking: string;
};

declare global {
  interface Window {
    glance: {
      getStatus: () => Promise<GlanceStatus>;
      quitGlance: () => Promise<void>;
    };
  }
}

function App() {
  const [status, setStatus] = useState<GlanceStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    window.glance.getStatus().then((nextStatus) => {
      setStatus(nextStatus);
      setError(null);
    }).catch((nextError: unknown) => {
      setStatus({ core: 'error', helper: 'unknown', tracking: 'unknown' });
      setError(nextError instanceof Error ? nextError.message : 'Unable to connect to Glance Core');
    });
  }, []);

  async function refreshStatus() {
    try {
      setStatus(await window.glance.getStatus());
      setError(null);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : 'Unable to refresh status');
    }
  }

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">Glance MVP</p>
        <h1>Eye tracking control for macOS</h1>
        <p>
          This UI is intentionally thin. The Python Core and Swift Helper own the runtime path.
        </p>
      </section>

      <section className="panel">
        <div className="panelHeader">
          <h2>Status</h2>
          <button type="button" onClick={refreshStatus}>Refresh</button>
        </div>
        <dl>
          <div>
            <dt>Core</dt>
            <dd>{status?.core ?? 'loading'}</dd>
          </div>
          <div>
            <dt>Helper</dt>
            <dd>{status?.helper ?? 'loading'}</dd>
          </div>
          <div>
            <dt>Tracking</dt>
            <dd>{status?.tracking ?? 'loading'}</dd>
          </div>
        </dl>
        {error ? <p className="error">{error}</p> : null}
        <button className="danger" type="button" onClick={() => window.glance.quitGlance()}>
          Quit Glance
        </button>
      </section>
    </main>
  );
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
