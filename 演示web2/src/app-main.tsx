import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./mock/App";
import { I18nProvider } from "./mock/i18n/I18nProvider";
import "./mock/styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider>
      <App />
    </I18nProvider>
  </StrictMode>
);