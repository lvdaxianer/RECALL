/**
 * Recall · 应用入口
 *
 * 把本地字体、主题样式、App 组件依次挂载到 #root。
 *
 * @author lvdaxianerplus
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

// 本地字体（fontsource）必须先于样式表引入，以避免 FOUT（无样式文本闪烁）。
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";

import { App } from "./app/App";
import "./styles/theme.css";
import "./styles/global.css";

/**
 * 渲染 App 到 #root：使用 React 19 的 createRoot API。
 *
 * @author lvdaxianerplus
 */
// 非空断言：index.html 已确保 #root 存在
createRoot(document.getElementById("root") as HTMLElement).render(
  // StrictMode 开启 React 开发期双调用检查
  <StrictMode>
    <App />
  </StrictMode>,
);
