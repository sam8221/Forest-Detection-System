/**
 * ===========================================================
 * ForestWatch Zambia
 * -----------------------------------------------------------
 * Module: Application Entry Point
 *
 * Purpose:
 *   Mounts the React application into the page.
 *
 * Responsibilities:
 *   - Attach the application to the #root element.
 *   - Load the single global stylesheet.
 *
 * How it works:
 *   index.html contains one empty <div id="root">. This file
 *   is the module Vite names as the entry: it finds that
 *   element and hands control to <App />, which owns every
 *   screen from that point on.
 *
 *   The stylesheet is imported here rather than linked from
 *   index.html so that Vite processes it, fingerprints it and
 *   includes it in the production bundle.
 *
 *   Nothing else belongs in this file. Application state,
 *   routing and authentication all live in App.jsx.
 *
 * Author:
 *   Samuel Bikiloni
 *
 * Project:
 *   Web-Based Deforestation Detection and Alert System
 *   Using Sentinel-2 Imagery in the Copperbelt, Zambia
 * ===========================================================
 */

import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <App />
);