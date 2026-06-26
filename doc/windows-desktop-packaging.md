# Windows Desktop Packaging Scaffold

This project stays web-first during feature development:

- Frontend: `frontend/` with Vite and React.
- Backend: `backend/langdrill_agent/` with FastAPI.
- Desktop shell: `src-tauri/` prepared for Tauri 2.x.

## Development Flow

1. Start the backend API:
   ```bash
   python -m langdrill_agent.cli serve --reload
   ```
2. Start the web frontend:
   ```bash
   cd frontend
   npm run dev
   ```
3. Use the browser until the product flow is stable.

## Desktop Target

The final Windows app should use Tauri 2.x because it keeps the installer smaller than Electron and works well with the existing Vite build.

Planned desktop responsibilities:

- Open the React app in a native WebView2 window.
- Start or connect to the local FastAPI backend.
- Store the SQLite database and user settings in an app data directory.
- Add native file dialogs and screenshot/OCR import.
- Build NSIS/MSI installers for Windows.

## Future Commands

After adding Tauri dependencies and Rust toolchain:

```bash
cd frontend
npm install -D @tauri-apps/cli
npm run tauri:dev
npm run tauri:build
```

The current scaffold intentionally does not force Tauri installation yet, so normal web development and CI builds remain unchanged.
