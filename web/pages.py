"""HTML and CSS served by the teardown site."""
import html as html_mod
import time

from jobs import JOBS

CSS = """
:root {
  --paper: #f7f6f2;
  --paper-card: #ffffff;
  --paper-hover: #efeee8;
  --paper-active: #e7e6e0;
  --forest: #2f4632;
  --forest-hover: #243827;
  --terracotta: #b3562e;
  --terracotta-hover: #9c4925;
  --hair: #e0dfd6;
  --hair-dark: #c7c6bd;
  --mut: #5c6154;
  --body-ink: #26261f;

  /* Compatibility aliases */
  --green: #2f4632;
  --green-hover: #243827;
  --terra: #b3562e;
  --ink: #2f4632;

  --font-serif: "Newsreader", Georgia, serif;
  --font-sans: "IBM Plex Sans", system-ui, -apple-system, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: var(--font-sans);
  background: var(--paper);
  color: var(--body-ink);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}



.mono-label {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--mut);
  font-variant-numeric: tabular-nums;
}

.material-symbols-outlined {
  font-family: 'Material Symbols Outlined';
  font-weight: normal;
  font-style: normal;
  font-size: 18px;
  line-height: 1;
  letter-spacing: normal;
  text-transform: none;
  display: inline-block;
  white-space: nowrap;
  word-wrap: normal;
  direction: ltr;
  -webkit-font-feature-settings: 'liga';
  -webkit-font-smoothing: antialiased;
  vertical-align: middle;
}

a {
  color: var(--forest);
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

.mut {
  color: var(--mut);
  font-family: var(--font-sans);
  font-size: 13px;
  line-height: 1.5;
}

.dot {
  color: var(--terracotta);
}

.pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--forest);
  color: var(--forest);
  border-radius: 6px;
  padding: 8px 18px;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  background: transparent;
  cursor: pointer;
  text-decoration: none;
  transition: background 0.15s ease, color 0.15s ease, border-color 0.15s ease;
  user-select: none;
}

.pill:hover {
  background: var(--paper-hover);
  text-decoration: none;
}

.pill.solid {
  background: var(--forest);
  color: #fff;
  border-color: var(--forest);
}

.pill.solid:hover {
  background: var(--forest-hover);
  border-color: var(--forest-hover);
}

.card {
  border: 1px solid var(--hair);
  background: var(--paper-card);
  border-radius: 8px;
}

.err {
  background: #fdf0ec;
  border: 1px solid #eec4b8;
  color: var(--terracotta);
  padding: 12px 16px;
  border-radius: 6px;
  font-family: var(--font-sans);
  font-size: 13px;
  margin-bottom: 20px;
}

/* LANDING PAGE (INDEX) STYLES */
.landing-page {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--paper);
}

.landing-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: var(--paper);
  border-bottom: 1px solid var(--hair);
}

.landing-container {
  width: 100%;
  max-width: 780px;
  margin: 0 auto;
  padding: 40px 20px 60px 20px;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.landing-hero {
  text-align: center;
  margin-bottom: 32px;
}

.landing-headline {
  font-family: var(--font-serif);
  font-size: 38px;
  line-height: 1.2;
  color: var(--forest);
  letter-spacing: -0.02em;
  font-weight: 400;
  margin-bottom: 12px;
}

.err, .landing-error {
  color: var(--terra);
  font-family: var(--font-sans);
  font-size: 13px;
  margin-bottom: 16px;
}

.landing-card {
  background: var(--paper-card);
  border: 1px solid var(--hair);
  border-radius: 12px;
  padding: 28px;
  margin-bottom: 16px;
}

.drop-zone {
  border: 1.5px dashed var(--hair);
  border-radius: 8px;
  padding: 36px 20px;
  text-align: center;
  background: var(--paper);
  transition: border-color 0.15s ease, background 0.15s ease;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.drop-zone:hover, .drop-zone.drag-over {
  border-color: var(--forest);
  background: var(--paper-hover);
}

.drop-title {
  font-family: var(--font-serif);
  font-weight: 500;
  font-size: 20px;
  color: var(--forest);
}

.drop-sub {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--mut);
  margin-bottom: 6px;
}

.drop-browse-pill {
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  background: var(--paper-card);
  border: 1px solid var(--hair);
  border-radius: 6px;
  color: var(--forest);
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  transition: all 0.15s ease;
}

.drop-browse-pill:hover {
  border-color: var(--forest);
  background: var(--paper-hover);
}

.landing-or-divider {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin: 22px 0;
}

.or-line {
  flex: 1;
  height: 1px;
  background: var(--hair);
}

.or-text {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--mut);
  text-transform: lowercase;
}

.url-input-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.url-label {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--mut);
}

.url-input-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.url-input-wrap {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
}

.url-icon {
  position: absolute;
  left: 14px;
  color: var(--mut);
  font-size: 18px;
  pointer-events: none;
}

.url-input {
  width: 100%;
  padding: 11px 16px 11px 40px;
  border: 1px solid var(--hair);
  border-radius: 6px;
  background: var(--paper);
  color: var(--body-ink);
  font-family: var(--font-sans);
  font-size: 13.5px;
  outline: none;
  transition: border-color 0.15s ease;
}

.url-input:focus {
  border-color: var(--forest);
}

.submit-pill {
  padding: 11px 22px;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.landing-subbar {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--mut);
  margin-bottom: 36px;
  text-align: center;
}

.recent-guides-section {
  margin-top: 10px;
  margin-bottom: 40px;
}

.recent-guides-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  border-bottom: 1px solid var(--hair);
  padding-bottom: 8px;
  margin-bottom: 14px;
}

.recent-guides-title {
  font-family: var(--font-serif);
  font-weight: 500;
  font-size: 20px;
  color: var(--forest);
}

.jobs-list {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--hair);
  border-radius: 8px;
  background: var(--paper-card);
  overflow: hidden;
}

.job-card {
  padding: 14px 18px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--hair);
  background: transparent;
  transition: background 0.15s ease;
  margin: 0;
  border-radius: 0;
}

.job-card:last-child {
  border-bottom: none;
}

.job-card:hover {
  background: var(--paper-hover);
}

.job-card .pill {
  border: none;
  padding: 0;
  border-radius: 0;
  font-size: 14px;
  font-weight: 500;
  display: inline-block;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.job-card {
  gap: 12px;
}

.job-card > .mut {
  flex-shrink: 0;
  white-space: nowrap;
}

.job-card .mut {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--mut);
}

.landing-footer {
  text-align: center;
  margin-top: auto;
  padding-top: 24px;
  border-top: 1px solid var(--hair);
}

@media (max-width: 600px) {
  .landing-headline {
    font-size: 28px;
  }
  .landing-card {
    padding: 18px;
  }
  .drop-zone {
    padding: 24px 14px;
  }
  .url-input-row {
    flex-direction: column;
    align-items: stretch;
  }
  .submit-pill {
    width: 100%;
    justify-content: center;
  }
}

/* APP HEADER & SUBBAR */
.app-header {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  background: var(--paper);
  border-bottom: 1px solid var(--hair);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand {
  font-family: var(--font-serif);
  font-size: 24px;
  font-weight: 500;
  color: var(--forest);
  text-decoration: none;
  letter-spacing: -0.3px;
}

.header-center {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  padding: 0 16px;
  min-width: 0;
}

.header-device {
  font-family: var(--font-serif);
  font-weight: 500;
  font-size: 16px;
  color: var(--forest);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-pdf {
  font-size: 12px;
  padding: 6px 14px;
  gap: 4px;
}

.app-subbar {
  background: #faf3ee;
  border-bottom: 1px solid var(--hair);
  border-left: 4px solid var(--terracotta);
  padding: 10px 20px;
  font-family: var(--font-sans);
  font-size: 14px;
  letter-spacing: 0;
  color: var(--body-ink);
  text-align: left;
}

/* VIDEO PLAYER & TIMELINE */
.player-pane {
  display: flex;
  flex-direction: column;
}

.video-frame {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #000;
  border: 1px solid var(--hair);
  border-bottom: none;
  overflow: hidden;
  max-height: 38vh;
  display: flex;
  align-items: center;
  justify-content: center;
}

.video-frame video {
  width: 100%;
  height: 100%;
  max-height: 38vh;
  display: block;
  object-fit: contain;
  background: #000;
}

@media (max-height: 480px) {
  .video-frame { max-height: 30vh !important; }
  .video-frame video { max-height: 30vh !important; }
}

.video-loading {
  position: absolute;
  top: 10px;
  right: 10px;
  background: var(--paper-card);
  color: var(--mut);
  border: 1px solid var(--hair);
  border-radius: 999px;
  padding: 3px 10px;
  font-family: var(--font-mono);
  font-size: 11px;
  pointer-events: none;
  z-index: 5;
  transition: opacity 0.2s ease;
}

.video-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  padding: 24px 20px;
  background: #faf6ee;
  color: var(--mut);
  text-align: center;
  gap: 4px;
}

.v-error-icon {
  color: var(--terracotta);
  font-size: 20px;
  margin-bottom: 2px;
}

.v-error-msg {
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 15px;
  color: var(--forest);
}

.v-error-sub {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--mut);
  max-width: 280px;
  line-height: 1.4;
}

/* TIMELINE CONTAINER & SEGMENTS */
.timeline-container {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--paper-card);
  border: 1px solid var(--hair);
  padding: 10px 14px;
}

.timeline-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.timeline-step-label {
  color: var(--mut);
}

.timeline-est {
  color: var(--forest);
  font-weight: 600;
}

.progress-bar {
  display: flex;
  gap: 3px;
  width: 100%;
  min-height: 28px;
  background: transparent;
  border: none;
}

.progress-seg {
  flex: 1;
  min-height: 28px;
  border-radius: 2px;
  cursor: pointer;
  background: transparent;
  border: 1px solid var(--hair);
  transition: background-color 0.15s ease, border-color 0.15s ease;
}

.progress-seg:hover {
  border-color: var(--forest);
}

.progress-seg.done {
  background: var(--forest);
  border: 1px solid var(--forest);
}

.progress-seg.active {
  background: var(--terracotta);
  border: 1px solid var(--terracotta);
}

/* TELEMETRY CARD */
.telemetry-card {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--paper-card);
  border: 1px solid var(--hair);
  border-radius: 8px;
}

.telemetry-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--hair);
}

.telemetry-pct {
  color: var(--terracotta);
  font-weight: 600;
}

.telemetry-step {
  color: var(--forest);
  font-weight: 600;
}

.telemetry-rem {
  color: var(--mut);
}

.telemetry-tray {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--hair);
}

.telemetry-tray-header {
  display: flex;
  align-items: center;
  gap: 4px;
  color: var(--mut);
}

.telemetry-tray-header .tray-icon {
  font-size: 15px;
  color: var(--terracotta);
}

.telemetry-tray-body {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.tray-chip {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  background: var(--paper);
  border: 1px solid var(--hair);
  border-radius: 4px;
  padding: 5px 8px;
  font-size: 12px;
}

.tray-chip-tag {
  color: var(--terracotta);
  font-weight: 600;
  font-size: 10px;
  flex-shrink: 0;
  padding-top: 1px;
}

.tray-chip-val {
  color: var(--body-ink);
  line-height: 1.3;
}

.tray-empty {
  color: var(--mut);
  font-size: 11px;
  font-style: italic;
  padding: 4px 0;
}

/* STEP CARD & CONTENTS */
.step-pane {
  display: flex;
  flex-direction: column;
}

.step-card {
  border: 1px solid var(--hair);
  border-radius: 8px;
  background: var(--paper-card);
  padding: 24px;
}

.step-item {
  display: none;
}

.step-item.active {
  display: block;
}

.step-eyebrow-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 10px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--hair);
}

.step-badge {
  color: var(--mut);
  font-weight: 500;
  padding: 3px 0;
}

.step-hl-badge {
  display: inline-flex;
  align-items: center;
  color: var(--terracotta);
  font-weight: 600;
}

.step-title {
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 26px;
  line-height: 1.25;
  color: var(--forest);
  margin-bottom: 12px;
}

.step-chips-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  margin-bottom: 16px;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 4px 9px;
  background: #ffffff;
  border: 1px solid var(--hair);
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--body-ink);
  line-height: 1.2;
  white-space: normal;
  word-break: break-word;
}

.chip-icon {
  font-size: 14px;
  color: var(--forest);
  flex-shrink: 0;
}

.chip-hl {
  border-color: var(--hair-dark);
}

.step-meta {
  font-size: 12px;
  color: var(--mut);
  margin-bottom: 14px;
  font-variant-numeric: tabular-nums;
}

.step-hl {
  color: var(--terracotta);
}

.step-image-wrap {
  position: relative;
  width: 100%;
  aspect-ratio: 16 / 9;
  background: #181917;
  border: 1px solid var(--hair);
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
  cursor: pointer;
}

.step-img {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.inspect-btn {
  position: absolute;
  bottom: 8px;
  left: 8px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: rgba(255, 255, 255, 0.94);
  border: 1px solid var(--hair);
  border-radius: 6px;
  padding: 3px 10px;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--forest);
  cursor: pointer;
  pointer-events: none;
}

.step-desc {
  font-family: var(--font-sans);
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--body-ink);
  margin-bottom: 16px;
}

/* HARDWARE & FASTENER REGISTRY BLOCK */
.step-registry {
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--paper);
  border: 1px solid var(--hair);
  border-radius: 6px;
  padding: 12px 14px;
  margin-bottom: 16px;
}

.registry-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.registry-icon {
  font-size: 16px;
  color: var(--terracotta);
}

.registry-title {
  color: var(--forest);
  font-weight: 600;
}

.registry-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.registry-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 13px;
  line-height: 1.4;
}

.registry-type {
  color: var(--forest);
  font-weight: 600;
  font-size: 11px;
  flex-shrink: 0;
  padding-top: 1px;
}

.registry-val {
  color: var(--body-ink);
}

/* CAUTION BOX */
.step-caution {
  border: 1px solid var(--hair);
  border-left: 3px solid var(--terracotta);
  background: #faf3ee;
  padding: 12px 14px;
  margin-bottom: 16px;
  border-radius: 0 6px 6px 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.caution-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.caution-icon {
  color: var(--terracotta);
  font-size: 16px;
}

.caution-eyebrow {
  color: var(--terracotta);
  font-weight: 700;
}

.caution-text {
  font-family: var(--font-sans);
  font-size: 13px;
  line-height: 1.5;
  color: #7c3a1e;
}

/* STEP NAVIGATION */
.step-nav {
  display: flex;
  gap: 10px;
  margin-top: 20px;
  padding-top: 18px;
  border-top: 1px solid var(--hair);
  align-items: center;
}

.nav-btn {
  padding: 10px 18px;
  font-size: 13px;
  min-height: 42px;
}

.nav-btn.primary-action {
  flex: 1.4;
}

.nav-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  pointer-events: none;
}

.bookmark-btn {
  width: 42px;
  height: 42px;
  padding: 0;
  flex-shrink: 0;
}

.bookmark-btn.bookmarked {
  background: var(--paper-active);
  color: var(--terracotta);
  border-color: var(--terracotta);
}

.step-nav-shortcuts {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 10px;
  padding: 0 4px;
}

.step-nav-shortcuts kbd {
  padding: 2px 6px;
  border: 1px solid var(--hair);
  border-radius: 4px;
  background: var(--paper);
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--forest);
}

/* STEPS DISCLOSURE & RAIL */
.disclosure-pane {
  display: flex;
  flex-direction: column;
}

.steps-disclosure {
  border: 1px solid var(--hair);
  border-radius: 8px;
  background: var(--paper-card);
  overflow: hidden;
}

.disclosure-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  cursor: pointer;
  background: var(--paper-active);
  border-bottom: 1px solid var(--hair);
  list-style: none;
  gap: 12px;
  user-select: none;
}

.disclosure-summary::-webkit-details-marker,
.disclosure-summary::marker {
  display: none;
}

.disclosure-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.disclosure-icon {
  font-size: 18px;
  color: var(--forest);
}

.disclosure-title {
  font-family: var(--font-sans);
  font-weight: 600;
  font-size: 16px;
  font-weight: 500;
  color: var(--forest);
}

.disclosure-count {
  color: var(--mut);
}

.disclosure-toggle {
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--forest);
  font-weight: 600;
  flex-shrink: 0;
}

.steps-index-search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--paper);
  border-bottom: 1px solid var(--hair);
}

.search-icon {
  font-size: 18px;
  color: var(--mut);
}

.steps-search-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  font-family: var(--font-sans);
  font-size: 13px;
  color: var(--body-ink);
}

.steps-search-input::placeholder {
  color: var(--mut);
}

.rail-list {
  max-height: 480px;
  overflow-y: auto;
}

.rail-row {
  display: grid;
  grid-template-columns: 28px 60px 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--hair);
  cursor: pointer;
  background: transparent;
  transition: background 0.1s ease;
  user-select: none;
}

.rail-row:last-child {
  border-bottom: none;
}

.rail-row:hover {
  background: var(--paper-hover);
}

.rail-row.active {
  background: var(--paper-active);
  border-left: 3px solid var(--terracotta);
  padding-left: 11px;
}

.row-num {
  font-size: 12px;
  font-weight: 600;
  color: var(--forest);
  text-align: center;
}

.rail-row.active .row-num {
  color: var(--terracotta);
}

.row-thumb-wrap {
  width: 60px;
  aspect-ratio: 16 / 9;
  border-radius: 4px;
  overflow: hidden;
  border: 1px solid var(--hair);
  background: #181917;
  flex-shrink: 0;
}

.row-thumb {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.row-thumb-missing {
  display: flex; align-items: center; justify-content: center;
  font-size: 9px; color: var(--mut); background: var(--hair);
}

.row-content {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.row-title {
  font-family: var(--font-sans);
  font-size: 13.5px;
  font-weight: 500;
  color: var(--body-ink);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.rail-row.active .row-title {
  font-weight: 600;
  color: var(--forest);
}

.row-meta {
  color: var(--mut);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.row-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.status-icon {
  font-size: 18px;
  line-height: 1;
}

.icon-done {
  color: var(--forest);
}

.icon-active {
  color: var(--terracotta);
}

.icon-pending {
  color: var(--hair-dark);
}

.bookmark-row-indicator {
  color: var(--terracotta);
  font-size: 16px;
}

/* BANNER & FOOTER */
.notice-pane {
  display: flex;
  flex-direction: column;
}

.banner {
  border: 1px solid var(--hair);
  border-left: 3px solid var(--terracotta);
  background: var(--paper-card);
  padding: 12px 16px;
  font-family: var(--font-sans);
  font-size: 12px;
  color: var(--mut);
  line-height: 1.5;
  border-radius: 0 6px 6px 0;
}

.footer-pane {
  padding-top: 12px;
  text-align: center;
}

.app-footer {
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.05em;
  color: var(--mut);
}

/* MOBILE STICKY BOTTOM THUMB BAR */
.mobile-thumb-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 100;
  background: #ffffff;
  border-top: 1px solid var(--hair);
  padding: 10px 16px;
  padding-bottom: max(10px, env(safe-area-inset-bottom, 10px));
  display: flex;
  align-items: center;
  gap: 10px;
}

.thumb-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: 6px;
  font-family: var(--font-sans);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s ease, color 0.15s ease;
  user-select: none;
}

.thumb-prev {
  background: transparent;
  border: 1px solid var(--hair);
  color: var(--forest);
  height: 42px;
  padding: 0 16px;
}

.thumb-prev:disabled {
  opacity: 0.35;
  pointer-events: none;
}

.thumb-complete-next {
  flex: 1;
  background: var(--forest);
  border: 1px solid var(--forest);
  color: #fff;
  height: 42px;
  padding: 0 18px;
  font-weight: 600;
}

#thumb-complete-next-lbl { white-space: normal; font-size: 12.5px; text-align: center; }
.thumb-complete-next { min-width: 0; }
.thumb-complete-next:active {
  background: var(--forest-hover);
}

.thumb-bookmark {
  width: 42px;
  height: 42px;
  padding: 0;
  border-radius: 6px;
  background: transparent;
  border: 1px solid var(--hair);
  color: var(--forest);
  flex-shrink: 0;
}

.thumb-bookmark.bookmarked {
  background: var(--paper-active);
  color: var(--terracotta);
  border-color: var(--terracotta);
}

/* FULLSCREEN IMAGE OVERLAY */
.image-overlay {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: rgba(20, 22, 20, 0.9);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.image-overlay-box {
  background: var(--paper-card);
  border: 1px solid var(--hair);
  border-radius: 8px;
  max-width: 95vw;
  max-height: 95vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.image-overlay-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  border-bottom: 1px solid var(--hair);
  background: var(--paper);
}

.image-overlay-close-btn {
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--forest);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4px;
  border-radius: 50%;
}

.image-overlay-close-btn:hover {
  background: var(--paper-hover);
}

.image-overlay-body {
  padding: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: auto;
  cursor: zoom-out;
}

.image-overlay-body img {
  max-width: 90vw;
  max-height: 80vh;
  object-fit: contain;
  display: block;
  border: 1px solid var(--hair);
}

/* RESPONSIVE LAYOUTS */
@media (max-width: 1023px) {
  .step-nav, .step-nav-shortcuts { display: none; }
  .layout-container {
    padding: 0 0 90px 0;
  }
  .layout {
    display: flex;
    flex-direction: column;
  }
  .left-col, .right-col {
    display: contents;
  }
  .player-pane {
    order: 1;
    position: sticky;
    top: 0;
    z-index: 30;
    background: var(--paper);
    width: 100%;
  }
  .timeline-container {
    order: 2;
    border-left: none;
    border-right: none;
  }
  .step-pane {
    order: 3;
    padding: 16px 14px 0 14px;
    scroll-margin-top: calc(min(56.25vw, 38vh) + 64px);
  }
  .telemetry-card {
    display: none;
  }
  .disclosure-pane {
    order: 4;
    padding: 14px 14px 0 14px;
  }
  .notice-pane {
    order: 5;
    padding: 14px 14px 0 14px;
  }
  .footer-pane {
    order: 6;
    padding: 14px 14px 24px 14px;
  }
}

@media (min-width: 1024px) {
  .mobile-thumb-bar {
    display: none !important;
  }
  .layout-container {
    max-width: 1280px;
    margin: 0 auto;
    padding: 24px 28px 48px;
  }
  .layout {
    display: grid;
    grid-template-columns: 480px 1fr;
    gap: 32px;
    align-items: start;
  }
  .left-col {
    display: flex;
    flex-direction: column;
    position: sticky;
    top: 20px;
    gap: 16px;
  }
  .right-col {
    display: flex;
    flex-direction: column;
    gap: 20px;
    min-width: 0;
  }
  .player-pane {
    position: static;
    width: 100%;
  }
  .steps-disclosure {
    border: 1px solid var(--hair);
  }
  .disclosure-summary {
    pointer-events: none;
    cursor: default;
  }
  .disclosure-toggle {
    display: none;
  }
  .rail-list {
    max-height: calc(100vh - 380px);
    min-height: 260px;
  }
}
"""

CSS_EXTRA = """
.busy-wrap { max-width: 560px; margin: 64px auto; padding: 0 24px; }
.busy-card { padding: 40px 32px; text-align: center; }
.busy-title { font-weight: 500; font-size: 24px; margin: 16px 0 4px; }
.busy-stage { color: var(--body-ink); font-size: 15px; min-height: 22px; }
.busy-bar { height: 6px; background: var(--hair); border-radius: 3px; margin: 18px 0 10px; overflow: hidden; }
.busy-fill { height: 100%; width: 2%; background: var(--forest); border-radius: 3px; transition: width .6s ease; }
.busy-fill.indet { width: 40% !important; animation: busy-slide 1.4s ease-in-out infinite; }
@keyframes busy-slide { 0% { margin-left: -40%; } 100% { margin-left: 100%; } }
.busy-detail { color: var(--mut); font-size: 12px; min-height: 16px; }
.busy-elapsed { color: var(--mut); font-size: 12px; margin-top: 2px; }
.busy-note { color: var(--mut); font-size: 13px; margin-top: 18px; }
.busy-note a { color: var(--terracotta); }
.spinner { width: 26px; height: 26px; margin: 0 auto; border: 3px solid var(--hair); border-top-color: var(--forest); border-radius: 50%; animation: busy-spin .9s linear infinite; }
@keyframes busy-spin { to { transform: rotate(360deg); } }
.err-icon { font-size: 30px; color: var(--terracotta); }
.err-msg { color: var(--body-ink); font-size: 15px; margin-top: 12px; line-height: 1.6; }
.up-bar { height: 6px; background: var(--hair); border-radius: 3px; margin: 14px 0 8px; overflow: hidden; }
.up-fill { height: 100%; width: 0%; background: var(--forest); border-radius: 3px; transition: width .3s ease; }
.font-serif { font-family: var(--font-serif); }
.visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }
:focus-visible { outline: 2px solid var(--forest); outline-offset: 2px; }
.guide-cover { background: var(--paper-card); border: 1px solid var(--hair); border-radius: 8px; padding: 16px 18px; margin-bottom: 16px; }
.step-num { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 50%; background: var(--forest); color: #fff; font-size: 14px; margin-right: 8px; }
.guide-cover h1 { font-size: 28px; color: var(--forest); margin: 0 0 6px; }
.guide-cover h2 { font-size: 13px; color: var(--forest); margin: 12px 0 4px; }
.guide-cover ul { margin: 0; padding-left: 18px; }
.bullet-list { list-style: none; padding: 0; margin: 12px 0; }
.bullet-list li { margin: 6px 0; padding: 2px 0 2px 12px; border-left: 3px solid var(--forest); }
.bullet-list li.caution { border-color: var(--terracotta); color: #7c3a1e; }
.bullet-list li.note { border-color: var(--mut); }
.anchor-quote { display: block; margin: 8px 0; padding: 0; border: 0; background: transparent; color: var(--mut); font-family: var(--font-serif); font-style: italic; text-align: left; cursor: pointer; }
.filmstrip { display: flex; gap: 6px; margin-top: 8px; overflow-x: auto; }
.film-btn { border: 1px solid var(--hair); padding: 0; background: var(--paper); border-radius: 4px; cursor: pointer; }
.film-btn img { display: block; width: 72px; height: 40px; object-fit: cover; }
.precaution { border: 1px dashed var(--terracotta); color: #7c3a1e; padding: 8px 10px; margin-top: 8px; font-size: 13px; }
.reassembly-banner { background: #faf3ee; border-left: 4px solid var(--terracotta); padding: 8px 12px; margin-bottom: 12px; }
.rights-ack { display: flex; gap: 8px; align-items: flex-start; font-size: 13px; margin-top: 12px; color: var(--body-ink); }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
@media print {
  .player-pane, .mobile-thumb-bar, .step-nav, .step-nav-shortcuts, .app-header, .image-overlay, .telemetry-card, .header-pdf { display: none !important; }
  .step-item { display: block !important; break-inside: avoid; margin-bottom: 16px; }
  .layout, .layout-container, .right-col, .left-col { display: block !important; }
}
"""

_HEAD = """<!doctype html><html lang="en"><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>__TITLE__ - teardown</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" rel="stylesheet">
<style>__CSS__</style></head><body>
<header class="landing-header">
  <div class="header-left">
    <a href="/" class="brand font-serif">teardown<span class="dot">.</span></a>
  </div>
</header>
"""

BUSY = _HEAD + """
<div class="busy-wrap">
  <div class="card busy-card">
    <div class="spinner" aria-hidden="true"></div>
    <h2 class="font-serif busy-title">building your guide</h2>
    <p class="busy-stage" id="stage" aria-live="polite">__STAGE__</p>
    <div class="busy-bar"><div class="busy-fill indet" id="fill"></div></div>
    <p class="busy-detail mono-label" id="detail">__DETAIL__</p>
    <p class="busy-elapsed mono-label"><span id="elapsed">__ELAPSED__</span> elapsed</p>
    <p class="busy-note">a short clip takes a few minutes on this free demo server - longer videos take longer. you can leave this tab open; it updates itself.</p>
  </div>
</div>
<script>
var JOB = "__JOB__";
var dead = false;
function fmt(s){ s = s|0; var m = Math.floor(s/60); return m > 0 ? m + "m " + (s%60) + "s" : s + "s"; }
function showMissing(){
  dead = true;
  document.querySelector(".busy-card").innerHTML =
    '<h2 class="font-serif busy-title">this guide went away</h2>' +
    '<p class="busy-note">the demo server restarted or the guide expired - <a href="/">start a new one</a>.</p>';
}
function poll(){
  if (dead) return;
  fetch("/jobs/" + JOB + "/status.json", {cache: "no-store"}).then(function(r){
    if (r.status === 404) { showMissing(); return null; }
    return r.json();
  }).then(function(st){
    if (!st) return;
    if (st.status === "done" || st.status === "error") { location.reload(); return; }
    if (st.status === "missing") { showMissing(); return; }
    var stageText = st.stage || "working";
    document.getElementById("stage").textContent = stageText;
    document.title = stageText + " - teardown";
    document.getElementById("detail").textContent = st.detail || (st.pct === null || st.pct === undefined ? "planning has no sub-progress" : "");
    document.getElementById("elapsed").textContent = fmt(st.elapsed_s);
    var fill = document.getElementById("fill");
    if (st.pct === null || st.pct === undefined) {
      fill.classList.add("indet");
    } else {
      fill.classList.remove("indet");
      fill.style.width = Math.max(2, Math.min(100, st.pct)) + "%";
    }
  }).catch(function(){
    var detail = document.getElementById("detail");
    if (detail) detail.textContent = "lost contact with the server - still trying";
  });
  setTimeout(poll, 2000);
}
poll();
</script>
</body></html>"""

ERRPAGE = _HEAD + """
<div class="busy-wrap">
  <div class="card busy-card">
    <span class="material-symbols-outlined err-icon">error</span>
    <h2 class="font-serif busy-title">this guide didn't make it</h2>
    <p class="err-msg">__MSG__</p>
    <p class="busy-note"><a href="/">try another video</a></p>
  </div>
</div>
</body></html>"""

MISSING = _HEAD + """
<div class="busy-wrap">
  <div class="card busy-card">
    <span class="material-symbols-outlined err-icon">search_off</span>
    <h2 class="font-serif busy-title">guide not found</h2>
    <p class="err-msg">this guide expired, or the demo server restarted and lost it.</p>
    <p class="busy-note"><a href="/">start a new one</a></p>
  </div>
</div>
</body></html>"""


def _page(tpl, title):
    return tpl.replace("__CSS__", CSS + CSS_EXTRA).replace("__TITLE__", title)


def _busy_page(job, st):
    elapsed = int(time.time() - st.get("created", time.time()))
    return (_page(BUSY, "building guide")
            .replace("__JOB__", job)
            .replace("__STAGE__", html_mod.escape(st.get("stage") or "queued"))
            .replace("__DETAIL__", html_mod.escape(st.get("detail") or ""))
            .replace("__ELAPSED__", f"{elapsed // 60}m {elapsed % 60}s" if elapsed >= 60 else f"{elapsed}s"))


def _error_page(msg):
    return _page(ERRPAGE, "guide failed").replace("__MSG__", html_mod.escape(msg))


def _missing_page():
    return _page(MISSING, "guide not found")


INDEX = """<!doctype html><html lang="en"><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>teardown</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" rel="stylesheet">
<style>__CSS__</style>
__REFRESH__</head><body class="landing-page">
<!-- __DEVICE__ -->
<header class="landing-header">
  <div class="header-left">
    <a href="/" class="brand font-serif">teardown<span class="dot">.</span></a>
  </div>
</header>

<div class="landing-container">
  <section class="landing-hero">
    <h1 class="landing-headline font-serif">repair footage in, illustrated guide out</h1>
  </section>

  __ERROR__

  <div class="card landing-card">
    <form method="post" action="/jobs" enctype="multipart/form-data" class="landing-form">
      <input type="hidden" name="csrf" value="__CSRF__">
      <div class="drop-zone" id="drop-zone">
        <div class="drop-title font-serif">drop a video here</div>
        <p class="drop-sub mono-label">mp4 or mov, up to 150 MB and 20 minutes. Narration is required. A 20-minute clip often takes 10 to 25 minutes, and the server builds one guide at a time.</p>
        <label for="f" class="pill drop-browse-pill">
          <span class="material-symbols-outlined" aria-hidden="true" style="font-size:16px;">folder_open</span>
          <span id="browse-label">browse files</span>
          <input id="f" type="file" name="video" accept="video/mp4,video/quicktime,video/*" style="display:none;">
        </label>
      </div>

      <div class="landing-or-divider">
        <span class="or-line"></span>
        <span class="or-text mono-label">or</span>
        <span class="or-line"></span>
      </div>

      <div class="url-input-section">
        <div class="url-input-row">
          <div class="url-input-wrap">
            <span class="material-symbols-outlined url-icon">link</span>
            <input type="text" id="url-input" name="url" placeholder="paste a youtube link" aria-label="YouTube link" class="url-input">
          </div>
          <button class="pill solid submit-pill" type="submit">
            <span>build guide</span>
            <span class="material-symbols-outlined" aria-hidden="true" style="font-size:16px;">arrow_forward</span>
          </button>
        </div>
        <input type="text" name="attribution" id="attribution" class="url-input" placeholder="creator, license, source URL (optional)" aria-label="Footage attribution" style="margin-top:10px;width:100%;">
        <label class="rights-ack" for="rights">
          <input type="checkbox" name="rights" id="rights" value="yes" required>
          <span>I have the right to upload this footage, and I understand generated guides are not validated repair instructions.</span>
        </label>
      </div>
    </form>
  </div>

  <p class="landing-subbar">public demo - generated guides are not validated repair instructions</p>
  <p class="landing-subbar" style="margin-top:8px">__TRAINING__ only upload video you have the right to share. guides auto-delete after 3 hours. you can leave the tab; the build keeps running.</p>

  <section class="recent-guides-section">
    <div class="recent-guides-header">
      <h2 class="recent-guides-title font-serif">your recent guides</h2>
    </div>
    <div class="jobs-list">
      __JOBS__
    </div>
  </section>

  <footer class="landing-footer">
    <p class="app-footer">public demo - shared $20 API budget - not repair advice</p>
  </footer>
</div>

<script>
const fileInput = document.getElementById('f');
if (fileInput) {
  fileInput.addEventListener('change', function(){
    const b = document.getElementById('browse-label');
    if (b) b.textContent = this.files[0] ? this.files[0].name : 'browse files';
  });
}
const dropZone = document.getElementById('drop-zone');
if (dropZone && fileInput) {
  ['dragenter', 'dragover'].forEach(function(name) {
    dropZone.addEventListener(name, function(e) {
      e.preventDefault();
      dropZone.classList.add('drag-over');
    });
  });
  ['dragleave', 'drop'].forEach(function(name) {
    dropZone.addEventListener(name, function(e) {
      e.preventDefault();
      dropZone.classList.remove('drag-over');
    });
  });
  dropZone.addEventListener('drop', function(e) {
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      const b = document.getElementById('browse-label');
      if (b) b.textContent = fileInput.files[0].name;
    }
  });
}

// raw-bytes upload with a real progress bar; falls back to the plain
// form post when no file is chosen or JS fails before send()
const landingForm = document.querySelector('.landing-form');
if (landingForm) {
  landingForm.addEventListener('submit', function(ev){
    const rights = document.getElementById('rights');
    if (rights && !rights.checked) {
      ev.preventDefault();
      return;
    }
    const fi = document.getElementById('f');
    const urlVal = (document.getElementById('url-input').value || '').trim();
    if (!fi || !fi.files.length || urlVal) return;  // url path: normal submit
    ev.preventDefault();
    const file = fi.files[0];
    const dz = document.getElementById('drop-zone');
    dz.innerHTML = '<div class="drop-title font-serif" id="up-title"></div>' +
      '<div class="up-bar"><div class="up-fill" id="up-fill"></div></div>' +
      '<p class="drop-sub mono-label" id="up-label">starting upload</p>';
    document.getElementById('up-title').textContent = 'uploading ' + file.name;
    const btn = document.querySelector('.submit-pill');
    if (btn) btn.disabled = true;
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/jobs?filename=' + encodeURIComponent(file.name));
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    xhr.setRequestHeader('X-TD-CSRF', (document.querySelector('input[name=csrf]') || {}).value || '');
    xhr.setRequestHeader('X-TD-Rights', 'yes');
    const credit = document.getElementById('attribution');
    if (credit && credit.value) xhr.setRequestHeader('X-TD-Attribution', credit.value.slice(0, 200));
    xhr.upload.onprogress = function(e){
      if (!e.lengthComputable) return;
      const p = Math.round(100 * e.loaded / e.total);
      document.getElementById('up-fill').style.width = p + '%';
      document.getElementById('up-label').textContent =
        'uploading - ' + p + '% (' + Math.round(e.loaded / 1048576) +
        ' of ' + Math.round(e.total / 1048576) + ' MB)';
    };
    xhr.onload = function(){
      if (xhr.responseURL && xhr.responseURL.indexOf('/jobs/') !== -1) {
        location.href = xhr.responseURL;
      } else {
        document.open(); document.write(xhr.responseText); document.close();
      }
    };
    xhr.onerror = function(){
      location.href = '/?e=' + encodeURIComponent('upload failed - check your connection and try again');
    };
    xhr.send(file);
  });
}
function refreshJobs(){
  document.querySelectorAll('[data-job]').forEach(function(node){
    fetch('/jobs/' + node.getAttribute('data-job') + '/status.json', {cache: 'no-store'})
      .then(function(r){ return r.ok ? r.json() : null; })
      .then(function(st){
        if (!st) return;
        if (st.status === 'done') location.reload();
        var label = node.querySelector('.job-live-label');
        if (label) label.textContent = st.stage || st.status || 'working';
      }).catch(function(){});
  });
}
if (document.querySelector('[data-job]')) setInterval(refreshJobs, 4000);
</script>
</body></html>"""


GUIDE = """<!doctype html><html lang="en"><head><meta charset=utf-8>
<meta name=viewport content="width=device-width, initial-scale=1">
<title>__DEVICE__ - teardown</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;1,6..72,400&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200" rel="stylesheet">
<style>__CSS__</style></head><body>
<header class="app-header">
  <div class="header-left">
    <a href="/" class="brand">teardown<span class="dot">.</span></a>
  </div>
  <div class="header-center">
    <span class="header-device">__DEVICE__</span>
  </div>
  <div class="header-right">
    <a class="pill header-pdf" href="/jobs/__JOB__/guide.pdf" download="teardown-guide.pdf" onclick="this.querySelector('span.dl-label').textContent='Preparing PDF…'">
      <span class="material-symbols-outlined" aria-hidden="true" style="font-size:16px; margin-right:4px;">download</span><span class="dl-label">PDF</span>
    </a>
  </div>
</header>
<div class="app-subbar">Demo output, not validated repair instructions. Times are about ±30 seconds. Highlights are drawn only when segmentation matches the named part directly.</div>

<main class="layout-container">
  <div class="layout">
    <div class="left-col">
      <div class="player-pane">
        <div class="video-frame">
          <video id="v" controls playsinline preload="metadata" poster="__POSTER__" src="/jobs/__JOB__/video.mp4" aria-label="Source footage"></video>
          <div id="v-loading" class="video-loading" aria-live="polite">loading footage&hellip;</div>
          <div id="v-error" class="video-error" style="display:none;" role="alert">
            <span class="v-error-icon">&#9888;</span>
            <p class="v-error-msg">Video footage unavailable</p>
            <p class="v-error-sub">Use the illustrated repair steps below.</p>
          </div>
        </div>
        <div class="timeline-container">
          <div class="timeline-header">
            <span class="mono-label timeline-step-label" id="timeline-step-label">Step 01 of __NSTEPS__ - active</span>
            <span class="mono-label timeline-est" id="timeline-est">about 00:00 (±30s)</span>
          </div>
          <div class="progress-bar" id="progress-bar" aria-label="Step progress">
            __PROGRESS__
          </div>
        </div>
      </div>
      <div class="telemetry-card card">
        <div class="telemetry-top">
          <div class="telemetry-pct mono-label" id="telemetry-pct">0% completed</div>
        </div>
        <div class="telemetry-tray">
          <div class="telemetry-tray-header mono-label">
            <span class="material-symbols-outlined tray-icon">tune</span>
            <span>Active step hardware</span>
          </div>
          <div class="telemetry-tray-body" id="telemetry-tray-body">
            <!-- Dynamic update via JS -->
          </div>
        </div>
      </div>
    </div>

    <div class="right-col">
      <section class="guide-cover" id="guide-cover">
        <h1 class="font-serif">__DEVICE__</h1>
        <p class="mono-label">__NSTEPS__ steps &middot; times are about &plusmn;30s</p>
        <h2>Tools in this video</h2>
        __TOOLS__
        <h2>Parts named</h2>
        __PARTS__
        __TRUNCATION__
        __ATTRIBUTION__
      </section>
      <div class="step-pane" id="step-pane">
        <p class="reassembly-banner" id="reassembly-banner" hidden>Reassembly order is this list reversed. Cable and fastener order was not verified.</p>
        <div class="step-card">
          <div id="step-cards-container">
            __STEPS__
          </div>
          <div class="step-nav">
            <button type="button" class="pill nav-btn" id="prev-btn" onclick="prevStep()" disabled>
              <span class="material-symbols-outlined" aria-hidden="true" style="font-size:16px; margin-right:4px;">arrow_back</span> Prev
            </button>
            <button type="button" class="pill solid nav-btn primary-action" id="complete-next-btn" onclick="completeAndNext()">
              <span id="complete-next-lbl">Complete &amp; Next: Step 02</span>
              <span class="material-symbols-outlined" aria-hidden="true" style="font-size:16px; margin-left:4px;">arrow_forward</span>
            </button>
            <button type="button" class="pill nav-btn" id="next-btn" onclick="nextStep()" title="Next without completing">
              <span>Next</span>
              <span class="material-symbols-outlined" aria-hidden="true" style="font-size:16px; margin-left:4px;">arrow_forward</span>
            </button>
            <button type="button" class="pill nav-btn" id="reassembly-btn" onclick="toggleReassembly()">Reassembly</button>
            <button type="button" class="pill bookmark-btn" id="bookmark-btn" onclick="toggleBookmark()" aria-pressed="false" aria-label="Bookmark step">
              <span class="material-symbols-outlined" aria-hidden="true" id="bookmark-icon">bookmark_border</span>
            </button>
          </div>
          <div class="step-nav-shortcuts">
            <span class="mono-label">Keyboard:</span>
            <span class="mono-label"><kbd>J</kbd> prev &middot; <kbd>K</kbd> next</span>
          </div>
        </div>
      </div>

      <div class="disclosure-pane">
        <details id="steps-disclosure" class="steps-disclosure">
          <summary class="disclosure-summary">
            <div class="disclosure-meta">
              <span class="material-symbols-outlined disclosure-icon">list_alt</span>
              <span class="disclosure-title">Complete Disassembly Manual</span>
              <span class="disclosure-count mono-label">__NSTEPS__ steps &middot; about &plusmn;30s</span>
            </div>
            <span class="disclosure-toggle">Hide list ▴</span>
          </summary>
          <div class="steps-index-content">
            <div class="steps-index-search-bar">
              <label class="visually-hidden" for="steps-search-input">Search steps</label>
              <span class="material-symbols-outlined search-icon">search</span>
              <input type="text" id="steps-search-input" class="steps-search-input" placeholder="Search procedure, screw, or tool..." aria-label="Search steps" oninput="filterSteps(this.value)">
            </div>
            <div class="rail-list" id="rail-list">
              __RAIL__
            </div>
          </div>
        </details>
      </div>

      <div class="notice-pane">
        <div class="banner">Auto-generated demo output - not validated repair instructions. Highlights appear only where the segmentation matched the named part directly; other steps show the plain frame.</div>
      </div>
      <footer class="footer-pane">
        <p class="app-footer">public demo - generated guides are not validated repair instructions</p>
      </footer>
    </div>
  </div>
</main>

<!-- MOBILE STICKY BOTTOM THUMB BAR -->
<aside class="mobile-thumb-bar" id="mobile-thumb-bar">
  <button type="button" class="thumb-btn thumb-prev" id="thumb-prev-btn" onclick="prevStep()" aria-label="Previous step">
    <span class="material-symbols-outlined" aria-hidden="true">arrow_back</span>
    <span>Prev</span>
  </button>
  <button type="button" class="thumb-btn thumb-complete-next" id="thumb-complete-next-btn" onclick="completeAndNext()">
    <span id="thumb-complete-next-lbl">Complete &amp; Next: Step 02</span>
    <span class="material-symbols-outlined" aria-hidden="true">arrow_forward</span>
  </button>
  <button type="button" class="thumb-btn thumb-next" id="thumb-next-btn" onclick="nextStep()" aria-label="Next step without completing">
    <span>Next</span>
  </button>
  <button type="button" class="thumb-btn thumb-bookmark" id="thumb-bookmark-btn" onclick="toggleBookmark()" aria-pressed="false" aria-label="Bookmark step">
    <span class="material-symbols-outlined" aria-hidden="true" id="thumb-bookmark-icon">bookmark_border</span>
  </button>
</aside>

<!-- FULLSCREEN IMAGE OVERLAY -->
<div id="image-overlay" class="image-overlay" style="display:none;" role="dialog" aria-modal="true" aria-label="Step photo" onclick="if(event.target===this)closeImageOverlay()">
  <div class="image-overlay-box">
    <div class="image-overlay-header">
      <span class="mono-label" id="image-overlay-title">STEP PHOTOGRAPHIC REFERENCE</span>
      <button type="button" class="image-overlay-close-btn" id="image-overlay-close-btn" onclick="closeImageOverlay()" aria-label="Close fullscreen view">
        <span class="material-symbols-outlined" aria-hidden="true">close</span>
      </button>
    </div>
    <div class="image-overlay-body">
      <img id="image-overlay-img" src="" alt="">
    </div>
  </div>
</div>

<script>
const stepTimes = __STEPTIMES__;
const stepHardware = __STEPHARDWARE__;
const totalSteps = stepTimes.length;
let activeStep = 0;

const JOB_ID = (location.pathname.match(/^\\/jobs\\/([\\w-]+)/) || [])[1] || 'unknown';
const LS_DONE = 'td4-done-' + JOB_ID;
const LS_BOOKMARKS = 'td4-bookmarks-' + JOB_ID;
let doneSteps = new Set();
let bookmarkSteps = new Set();

function loadStorage() {
  try {
    const d = localStorage.getItem(LS_DONE);
    if (d) {
      const arr = JSON.parse(d);
      if (Array.isArray(arr)) doneSteps = new Set(arr);
    }
  } catch(e) {}
  try {
    const b = localStorage.getItem(LS_BOOKMARKS);
    if (b) {
      const arr = JSON.parse(b);
      if (Array.isArray(arr)) bookmarkSteps = new Set(arr);
    }
  } catch(e) {}
}

function saveStorage() {
  try {
    localStorage.setItem(LS_DONE, JSON.stringify(Array.from(doneSteps)));
  } catch(e) {}
  try {
    localStorage.setItem(LS_BOOKMARKS, JSON.stringify(Array.from(bookmarkSteps)));
  } catch(e) {}
}

const v = document.getElementById('v');
const progressBar = document.getElementById('progress-bar');
const cardsContainer = document.getElementById('step-cards-container');
const railList = document.getElementById('rail-list');
const prevBtn = document.getElementById('prev-btn');
const nextBtn = document.getElementById('next-btn');
const completeNextLbl = document.getElementById('complete-next-lbl');
const thumbPrevBtn = document.getElementById('thumb-prev-btn');
const thumbCompleteNextLbl = document.getElementById('thumb-complete-next-lbl');
const bookmarkBtn = document.getElementById('bookmark-btn');
const bookmarkIcon = document.getElementById('bookmark-icon');
const thumbBookmarkBtn = document.getElementById('thumb-bookmark-btn');
const thumbBookmarkIcon = document.getElementById('thumb-bookmark-icon');
const disclosure = document.getElementById('steps-disclosure');
const vLoading = document.getElementById('v-loading');
const vErr = document.getElementById('v-error');

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function formatRemaining(idx) {
  const t = stepTimes[idx] || 0;
  const dur = (v && isFinite(v.duration) && v.duration > 0) ? v.duration : (stepTimes.length ? stepTimes[stepTimes.length - 1] : 0);
  const rem = Math.max(0, dur - t);
  const mins = Math.floor(rem / 60);
  const secs = Math.floor(rem % 60);
  return 'Video left ' + mins + 'm ' + secs + 's';
}

function updateStateUI() {
  const idx = activeStep;
  const remText = formatRemaining(idx);
  const stepNumStr = String(idx + 1).padStart(2, '0');

  // Timeline header
  const timelineStepLabel = document.getElementById('timeline-step-label');
  if (timelineStepLabel) timelineStepLabel.textContent = 'Step ' + stepNumStr + ' of ' + totalSteps + ' - active';
  const timelineEst = document.getElementById('timeline-est');
  if (timelineEst) timelineEst.textContent = remText;

  // Segments
  if (progressBar) {
    const segs = progressBar.children;
    for (let i = 0; i < segs.length; i++) {
      segs[i].classList.remove('done', 'active');
      if (doneSteps.has(i)) {
        segs[i].classList.add('done');
      }
      if (i === idx) {
        segs[i].classList.add('active');
      }
    }
  }

  // Telemetry Card
  const pctEl = document.getElementById('telemetry-pct');
  if (pctEl) {
    const pct = Math.round((doneSteps.size / totalSteps) * 100);
    pctEl.textContent = pct + '% completed';
  }
  const telemetryStep = document.getElementById('telemetry-step');
  if (telemetryStep) telemetryStep.textContent = 'Step ' + stepNumStr + ' of ' + totalSteps;
  const telemetryRem = document.getElementById('telemetry-rem');
  if (telemetryRem) telemetryRem.textContent = remText;

  const trayEl = document.getElementById('telemetry-tray-body');
  if (trayEl) {
    const hw = stepHardware[idx];
    let trayHtml = '';
    if (hw && (hw.fasteners || hw.connectors)) {
      if (hw.fasteners) {
        trayHtml += '<div class="tray-chip"><span class="tray-chip-tag mono-label">Fastener:</span><span class="tray-chip-val">' + escapeHtml(hw.fasteners) + '</span></div>';
      }
      if (hw.connectors) {
        trayHtml += '<div class="tray-chip"><span class="tray-chip-tag mono-label">CONNECTOR:</span><span class="tray-chip-val">' + escapeHtml(hw.connectors) + '</span></div>';
      }
    } else {
      trayHtml = '<div class="tray-empty mono-label">None for this step</div>';
    }
    trayEl.innerHTML = trayHtml;
  }

  // Nav buttons
  if (prevBtn) prevBtn.disabled = (idx === 0);
  if (thumbPrevBtn) thumbPrevBtn.disabled = (idx === 0);
  if (nextBtn) nextBtn.disabled = (idx === totalSteps - 1);

  const nextNumStr = String(idx + 2).padStart(2, '0');
  const completeLblText = (idx < totalSteps - 1) ? ('Complete & Next: Step ' + nextNumStr) : ('Complete: Step ' + stepNumStr);
  if (completeNextLbl) completeNextLbl.textContent = completeLblText;
  if (thumbCompleteNextLbl) thumbCompleteNextLbl.textContent = completeLblText;

  // Bookmark buttons
  const isBookmarked = bookmarkSteps.has(idx);
  if (bookmarkBtn) {
    bookmarkBtn.classList.toggle('bookmarked', isBookmarked);
    bookmarkBtn.setAttribute('aria-pressed', isBookmarked ? 'true' : 'false');
  }
  if (bookmarkIcon) bookmarkIcon.textContent = isBookmarked ? 'bookmark' : 'bookmark_border';
  if (thumbBookmarkBtn) {
    thumbBookmarkBtn.classList.toggle('bookmarked', isBookmarked);
    thumbBookmarkBtn.setAttribute('aria-pressed', isBookmarked ? 'true' : 'false');
  }
  if (thumbBookmarkIcon) thumbBookmarkIcon.textContent = isBookmarked ? 'bookmark' : 'bookmark_border';

  // Rail rows
  if (railList) {
    const rows = railList.children;
    for (let i = 0; i < rows.length; i++) {
      rows[i].classList.toggle('active', i === idx);
      const sIcon = document.getElementById('status-icon-' + i);
      if (sIcon) {
        sIcon.classList.remove('icon-done', 'icon-active', 'icon-pending');
        if (i === idx) {
          sIcon.textContent = 'sync';
          sIcon.classList.add('icon-active');
        } else if (doneSteps.has(i)) {
          sIcon.textContent = 'check_circle';
          sIcon.classList.add('icon-done');
        } else {
          sIcon.textContent = 'radio_button_unchecked';
          sIcon.classList.add('icon-pending');
        }
      }
      const bInd = document.getElementById('bm-ind-' + i);
      if (bInd) {
        bInd.style.display = bookmarkSteps.has(i) ? 'inline-block' : 'none';
      }
    }
    if (rows[idx] && hasInteracted && disclosure && disclosure.open) {
      var motion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
      rows[idx].scrollIntoView({ block: 'nearest', behavior: motion });
    }
  }
}

function setStep(idx, andSeek) {
  if (idx < 0) idx = 0;
  if (idx >= totalSteps) idx = totalSteps - 1;
  activeStep = idx;

  if (cardsContainer) {
    const cards = cardsContainer.children;
    for (let i = 0; i < cards.length; i++) {
      cards[i].classList.toggle('active', i === idx);
    }
  }

  updateStateUI();

  if (andSeek && v) {
    expectedSeekTime = stepTimes[idx];
    v.currentTime = stepTimes[idx];
    v.play().catch(function(){});
  }
}

function selectStep(idx) {
  hasInteracted = true;
  setStep(idx, true);
  if (disclosure && window.innerWidth < 1024) {
    disclosure.open = false;
    const pane = document.getElementById('step-pane');
    if (pane) {
      pane.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
}

function prevStep() {
  if (activeStep > 0) {
    selectStep(activeStep - 1);
  }
}

function nextStep() {
  if (activeStep < totalSteps - 1) {
    selectStep(activeStep + 1);
  }
}

function completeAndNext() {
  doneSteps.add(activeStep);
  saveStorage();
  if (activeStep < totalSteps - 1) {
    selectStep(activeStep + 1);
  } else {
    updateStateUI();
  }
}

function toggleBookmark() {
  if (bookmarkSteps.has(activeStep)) {
    bookmarkSteps.delete(activeStep);
  } else {
    bookmarkSteps.add(activeStep);
  }
  saveStorage();
  updateStateUI();
}

function filterSteps(q) {
  const query = (q || '').trim().toLowerCase();
  const rows = document.querySelectorAll('.rail-row');
  for (let i = 0; i < rows.length; i++) {
    const title = rows[i].getAttribute('data-title') || '';
    if (!query || title.toLowerCase().indexOf(query) !== -1) {
      rows[i].style.display = '';
    } else {
      rows[i].style.display = 'none';
    }
  }
}

document.addEventListener('click', function(e) {
  const w = e.target.closest('.step-image-wrap');
  if (w && w.dataset.full) openImageOverlay(w.dataset.full, w.dataset.title || '');
});
var overlayReturn = null;
function openImageOverlay(src, title) {
  const overlay = document.getElementById('image-overlay');
  const img = document.getElementById('image-overlay-img');
  const titleEl = document.getElementById('image-overlay-title');
  if (overlay && img) {
    overlayReturn = document.activeElement;
    img.src = src;
    img.alt = title || 'Step photo';
    if (titleEl && title) titleEl.textContent = title;
    overlay.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    var closeBtn = document.getElementById('image-overlay-close-btn');
    if (closeBtn) closeBtn.focus();
  }
}

function closeImageOverlay() {
  const overlay = document.getElementById('image-overlay');
  if (overlay && overlay.style.display !== 'none') {
    overlay.style.display = 'none';
    document.body.style.overflow = '';
    if (overlayReturn && overlayReturn.focus) overlayReturn.focus();
  }
}

if (v) {
  if (v.readyState >= 2 && vLoading) {
    vLoading.style.display = 'none';
  }
  v.addEventListener('loadedmetadata', function() { updateStateUI(); });
  v.addEventListener('seeked', function() { expectedSeekTime = null; });
  if (vLoading) {
    v.addEventListener('loadeddata', function() { vLoading.style.display = 'none'; });
    v.addEventListener('canplay', function() { vLoading.style.display = 'none'; });
    v.addEventListener('playing', function() { vLoading.style.display = 'none'; });
    v.addEventListener('waiting', function() { vLoading.style.display = 'block'; });
  }
  v.addEventListener('error', function() {
    if (vLoading) vLoading.style.display = 'none';
    v.style.display = 'none';
    if (vErr) vErr.style.display = 'flex';
  });
  v.addEventListener('timeupdate', function() {
    const ct = v.currentTime;
    if (expectedSeekTime !== null) {
      if (Math.abs(ct - expectedSeekTime) > 1.5) {
        return; // stale position from before our programmatic seek landed
      }
      expectedSeekTime = null;
    }
    let idx = 0;
    for (let i = 0; i < stepTimes.length; i++) {
      if (ct >= stepTimes[i]) {
        idx = i;
      } else {
        break;
      }
    }
    if (idx !== activeStep) {
      setStep(idx, false);
    }
  });
}

function syncDisclosure() {
  if (disclosure) {
    if (window.innerWidth >= 1024) {
      disclosure.open = true;
    }
    const toggleLbl = disclosure.querySelector('.disclosure-toggle');
    if (toggleLbl && window.innerWidth < 1024) {
      toggleLbl.textContent = disclosure.open ? 'Hide list ▴' : 'Show list ▾';
    }
  }
}

if (disclosure) {
  disclosure.addEventListener('toggle', function() {
    const toggleLbl = disclosure.querySelector('.disclosure-toggle');
    if (toggleLbl && window.innerWidth < 1024) {
      toggleLbl.textContent = disclosure.open ? 'Hide list ▴' : 'Show list ▾';
    }
  });
}

window.addEventListener('resize', syncDisclosure);
syncDisclosure();

function childIndex(parent, node) {
  return Array.prototype.indexOf.call(parent.children, node);
}
document.addEventListener('click', function(e) {
  const row = e.target.closest && e.target.closest('.rail-row');
  if (row && railList && railList.contains(row)) {
    selectStep(childIndex(railList, row));
    return;
  }
  const seg = e.target.closest && e.target.closest('.progress-seg');
  if (seg && progressBar && progressBar.contains(seg)) {
    selectStep(childIndex(progressBar, seg));
    return;
  }
  const film = e.target.closest && e.target.closest('.film-btn');
  if (film) {
    const card = film.closest('.step-item');
    const img = card && card.querySelector('.step-img');
    if (img && film.dataset.src) img.src = film.dataset.src;
    return;
  }
  const quote = e.target.closest && e.target.closest('.anchor-quote');
  if (quote && v) {
    v.currentTime = parseFloat(quote.dataset.t || '0');
    v.play().catch(function(){});
  }
});
document.addEventListener('keydown', function(e) {
  const row = e.target.closest && e.target.closest('.rail-row, .progress-seg');
  if (row && (e.key === 'Enter' || e.key === ' ')) {
    e.preventDefault();
    if (row.classList.contains('rail-row') && railList) selectStep(childIndex(railList, row));
    else if (progressBar) selectStep(childIndex(progressBar, row));
    return;
  }
  if (e.key === 'Escape') {
    closeImageOverlay();
    return;
  }
  const tag = (e.target.tagName || '').toUpperCase();
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'VIDEO' || tag === 'BUTTON' || tag === 'A' || e.target.isContentEditable) return;
  if (e.key === 'j' || e.key === 'J' || e.key === 'ArrowLeft') {
    prevStep();
  }
  if (e.key === 'k' || e.key === 'K' || e.key === 'ArrowRight') {
    nextStep();
  }
});
function toggleReassembly() {
  var banner = document.getElementById('reassembly-banner');
  if (cardsContainer) reverseChildren(cardsContainer);
  if (railList) reverseChildren(railList);
  if (progressBar) reverseChildren(progressBar);
  stepTimes.reverse();
  stepHardware.reverse();
  if (banner) banner.hidden = !banner.hidden;
  setStep(0, true);
}
function reverseChildren(node) {
  var kids = Array.prototype.slice.call(node.children);
  kids.reverse().forEach(function(child){ node.appendChild(child); });
}

var hasInteracted = false;
var expectedSeekTime = null;
if (disclosure && window.innerWidth >= 1024) { disclosure.open = true; }
// Initialize storage and UI
loadStorage();
updateStateUI();
</script>
</body></html>"""


def job_card(j):
    st = JOBS[j]
    esc = html_mod.escape
    if st["status"] == "done":
        return (f'<div class="card job-card"><a class="pill" href="/jobs/{j}">{esc(st.get("device") or j)}</a>'
                f'<span class="mut"> {st.get("steps", "?")} steps</span></div>')
    if st["status"] in ("processing", "downloading", "queued"):
        return (f'<div class="card job-card" data-job="{j}"><a class="pill" href="/jobs/{j}">in progress</a>'
                f'<span class="mut job-live-label"> {esc(st.get("stage") or st["status"])}</span></div>')
    if st["status"] == "error":
        return (f'<div class="card job-card"><a class="pill" href="/jobs/{j}">failed</a>'
                f'<span class="err"> {esc(st.get("error", "unknown error"))}</span></div>')
    return '<div class="card job-card"><span class="mut">queued</span></div>'
