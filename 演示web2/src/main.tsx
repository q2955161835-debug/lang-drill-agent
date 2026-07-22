import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

function readHash(): string {
  return typeof window === "undefined" ? "" : window.location.hash;
}

function useHashRoute(): string {
  const [hash, setHash] = useState(readHash);
  useEffect(() => {
    const onChange = () => setHash(readHash());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return hash;
}

function MockFrame() {
  // 在 landing 上通过 hash 路由切换到 mock 演示前端
  // 使用 iframe 让 mock 的全局 CSS 与 landing 完全隔离，保证 1:1 还原
  const base = import.meta.env.BASE_URL;
  const appUrl = `${base}app.html`;
  return (
    <div className="mock-frame-wrapper">
      <a className="mock-back" href="#/" aria-label="返回首页">
        <span aria-hidden>←</span> 返回首页
      </a>
      <iframe className="mock-frame" src={appUrl} title="Lang Drill Agent 演示前端" />
    </div>
  );
}

function Root() {
  const hash = useHashRoute();
  if (hash === "#/app" || hash === "#app") {
    return <MockFrame />;
  }
  return <App />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Root />
  </StrictMode>
);
