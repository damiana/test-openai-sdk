
import { ChatKit, useChatKit } from "@openai/chatkit-react";
import "./App.css";

export default function App() {
  const { control } = useChatKit({
    api: {
      url: "http://localhost:8000/chatkit",
      domainKey: "local-dev",
    },
  });

  return (
    <main className="app">
      {/* <header className="app-header">
        <div className="brand">
          <div className="brand-icon">✦</div>

          <div>
            <h1>FinAI</h1>
            <p>Seu assistente financeiro inteligente</p>
          </div>
        </div>

        <div className="app-status">
          <span className="status-dot" />
          Ambiente de demonstração
        </div>
      </header> */}

      <section className="app-content">
        {/* <div className="intro">
          <span className="intro-label">ASSISTENTE FINANCEIRO</span>
          <h2>Suas finanças, mais simples.</h2>
          <p>
            Consulte seu saldo, acompanhe seus boletos e
            organize seus pagamentos em uma conversa.
          </p>
        </div> */}

        <div className="chat-container">
          <div className="chat-header">
            <div className="assistant-avatar">✦</div>

            <div>
              <strong>Assistente FinAI</strong>
              <span>Pronto para ajudar com suas finanças</span>
            </div>
          </div>

          <ChatKit control={control} className="chatkit" />
        </div>

        <footer className="app-footer">
          Protótipo demonstrativo
        </footer>
      </section>
    </main>
  );
}
