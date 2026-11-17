# Changelog

All notable changes to FileSweep are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-11-17

First public release - day 1 of "30 Windows tools in 30 days".

### Added
- Folder planning by file extension with 9 built-in categories and an `Other` fallback.
- Optional year/month subfolders based on each file's modified date.
- Reversible runs: every move is recorded in a journal before the first file is touched.
- `filesweep undo` (latest or a specific journal) restores files and removes now-empty category folders.
- Desktop app (Tkinter): preview table, options, organize, undo, open log folder.
- CLI: `plan`, `run`, `undo`, `journals`, `config`, `watch`, `gui`.
- Background `watch` mode for keeping folders tidy automatically.
- JSON configuration with custom categories, exclusions, minimum file age and a separate target root.
- One-file `.exe` builds (`build.ps1`) and a per-user installer with Desktop + Start Menu shortcuts (`install.ps1`).
- Safety rules: no overwrites, no deletes, hidden/system files and partial downloads skipped.
- 22 unit tests, GitHub Actions CI on Windows and Linux (Python 3.10 and 3.13).
- MIT license, bilingual documentation (English + Arabic).
