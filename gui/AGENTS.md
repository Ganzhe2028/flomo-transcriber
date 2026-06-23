# gui/ — Tauri v2 Desktop GUI

## OVERVIEW
Windows desktop app wrapping the Python pipeline. React 18 frontend + Rust/Tauri v2 backend. The Python workflow runs as a compiled sidecar binary (PyInstaller) spawned by the Rust process.

## STRUCTURE
```
gui/
├── src/
│   ├── App.tsx          # Main SPA (661 lines): settings, 4 actions, dark/light theme
│   ├── main.tsx         # ReactDOM mount
│   └── styles.css       # Design system: dark navy #0b1020, 8pt grid, btn-* variants
├── src-tauri/
│   ├── tauri.conf.json  # Window 1280×820, NSIS bundle, externalBin: flomo-sidecar
│   ├── Cargo.toml       # Rust deps: tauri v2, serde, dialog, shell plugins
│   ├── build.rs         # tauri_build::build() hook
│   ├── src/main.rs      # Rust entry: calls lib::run()
│   └── src/lib.rs       # Core (917 lines): settings CRUD, workflow spawn, stream events
│   └── capabilities/    # Permissions: core, dialog:open, shell:spawn sidecar, shell:kill
│   └── binaries/        # flomo-sidecar-x86_64-pc-windows-msvc.exe (PyInstaller output)
└── package.json         # npm: dev/build/sidecar/tauri:build:nsis
```

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| Change UI layout | `src/App.tsx` | 4 actions in sidebar, settings/log panels |
| Change styles | `src/styles.css` | CSS custom properties: `--space-*`, `--radius-*`, 4 btn variants |
| Change Tauri backend behavior | `src-tauri/src/lib.rs` | 5 commands: read/write settings, run/cancel workflow, open path |
| Change sidecar invocation | `src-tauri/src/lib.rs:run_workflow()` | Production: sidecar binary; Debug: local Python fallback |
| Change window/bundle config | `src-tauri/tauri.conf.json` | NSIS only, externalBin path |

## CONVENTIONS
- Settings stored in `.env` (LM Studio config) + `.flomo-gui-settings.json` (paths)
- Dark theme default; light theme via localStorage `flomo-theme`
- Two runtime modes: production (sidecar binary) vs debug (local `python scripts/guide.py`)
- Sidecar built via `scripts/build_gui_sidecar.py` → PyInstaller `--onefile --noconsole`

## ANTI-PATTERNS
- **NEVER bundle real user data** in the installer (raw/, store/, monthly/, etc. excluded)
- **NEVER call Python directly** from the frontend — all workflow goes through Rust `invoke`
- **NEVER change CSP** without understanding Tauri security model
