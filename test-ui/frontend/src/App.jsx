import { useCallback, useEffect, useState } from "react";
import { ChatKit, useChatKit } from "@openai/chatkit-react";
import "./App.css";

const runtime = window.__FINAI_CONFIG__ || {};
const apiURL = new URL(
  runtime.chatkitApiURL || import.meta.env.VITE_CHATKIT_API_URL || "http://localhost:8000/chatkit",
  window.location.origin,
).href;
const domainKey = runtime.domainKey || import.meta.env.VITE_CHATKIT_DOMAIN_KEY || "local-dev";
const sessionURL = new URL("/session", apiURL).href;
const localPreview = ["localhost", "127.0.0.1"].includes(window.location.hostname);
const productionConfigured = !import.meta.env.PROD || (
  (apiURL.startsWith("https://") || localPreview) && (domainKey !== "local-dev" || localPreview)
);

async function solicitarSessao(code, signal) {
  const response = await fetch(sessionURL, {
    method: "POST", headers: { "X-Demo-Code": code }, credentials: "omit", signal,
  });
  if (response.status === 401) throw new Error("Informe o código de acesso fornecido para a demonstração.");
  if (!response.ok) throw new Error("Não foi possível iniciar. Tente novamente mais tarde.");
  return (await response.json()).token;
}

function Conversa({ token, onSessionEnded }) {
  const authenticatedFetch = useCallback(async (input, init = {}) => {
    const headers = new Headers(init.headers ?? (input instanceof Request ? input.headers : {}));
    headers.set("Authorization", `Bearer ${token}`);
    const response = await fetch(input, { ...init, headers, credentials: "omit" });
    if (response.status === 401) onSessionEnded();
    return response;
  }, [token, onSessionEnded]);
  const { control } = useChatKit({
    api: { url: apiURL, domainKey, fetch: authenticatedFetch },
  });
  return <ChatKit control={control} className="chatkit" />;
}

export default function App() {
  const [token, setToken] = useState(null);
  const [codigo, setCodigo] = useState("");
  const [aviso, setAviso] = useState(productionConfigured ? "" : "Configure a URL HTTPS do backend e o domínio ChatKit antes de publicar.");
  const [carregando, setCarregando] = useState(productionConfigured);

  const iniciar = useCallback(async (code = "", signal) => {
    if (!productionConfigured) return;
    try {
      const newToken = await solicitarSessao(code, signal);
      if (signal?.aborted) return;
      setToken(newToken);
      setCodigo("");
      setAviso("");
    } catch (error) {
      if (error.name !== "AbortError") setAviso(error.message);
    } finally {
      if (!signal?.aborted) setCarregando(false);
    }
  }, []);

  useEffect(() => {
    if (!productionConfigured) return;
    const controller = new AbortController();
    solicitarSessao("", controller.signal)
      .then((newToken) => { if (!controller.signal.aborted) setToken(newToken); })
      .catch((error) => { if (error.name !== "AbortError") setAviso(error.message); })
      .finally(() => { if (!controller.signal.aborted) setCarregando(false); });
    return () => controller.abort();
  }, []);

  const encerrar = useCallback(() => {
    setToken(null);
    setAviso("Sessão encerrada ou servidor reiniciado. Inicie uma nova demonstração; os dados simulados serão restaurados.");
  }, []);

  return (
    <main className="app">
      <section className="app-content">
        <div className="chat-container">
          <div className="chat-header">
            <div className="assistant-avatar">✦</div>
            <div>
              <strong>Assistente FinAI</strong>
              <span>Pronto para ajudar com suas finanças</span>
            </div>
          </div>
          {token ? <Conversa token={token} onSessionEnded={encerrar} /> : (
            <form className="session-entry" onSubmit={(event) => { event.preventDefault(); setCarregando(true); iniciar(codigo); }}>
              <h2>Assistente Financeiro Inteligente</h2>
              <p>Consulte seus boletos e organize pagamentos em um ambiente de demonstração.</p>
              <p role="status">{aviso || "Preparando sua sessão…"}</p>
              <label htmlFor="demo-code">Código de acesso</label>
              <input id="demo-code" type="password" value={codigo}
                onChange={(event) => setCodigo(event.target.value)} autoComplete="off" />
              <button type="submit" disabled={carregando || !productionConfigured}>
                {carregando ? "Conectando…" : "Iniciar demonstração"}
              </button>
            </form>
          )}
        </div>
        <footer className="app-footer">
          Protótipo demonstrativo · Dados simulados e isolados por sessão.<br />
          Atualizar a página ou reiniciar o servidor inicia uma nova demonstração.
        </footer>
      </section>
    </main>
  );
}
