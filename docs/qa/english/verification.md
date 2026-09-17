# English UI Verification

Date: 2026-09-13 · Scope: English application text and documentation, with existing behavior preserved.

## Delivered

- Translated application-owned buttons, tabs, tooltips, settings, summaries, status messages, prompts, validation errors, and empty-state guidance.
- Updated the Selection/Full Track action values and dependent tests together; saved project schema and user filenames are unchanged.
- Translated README.txt, project.md, and the historical G01/G02–G08 reports. Historical measurements and screenshots remain intact; current English captures are stored separately here.
- Windows-owned file-picker controls, standard dialog buttons, and OS error text follow Windows language settings. User filenames keep their original language.
- The original app was open during delivery. It was not terminated or overwritten. The root launcher and future build.ps1 output now use the English release folder.

## Tests

```powershell
.\.build\qa\Scripts\python.exe -B -m pytest tests -q --capture=sys -p no:cacheprovider
```

Result: **48 passed, 18 subtests passed in 32.02s**.

New checks cover application string literals, actual Tk widget text, tooltips, English monitor/export summaries, and confirmation dialogs. The existing Unicode project-filename fixture is preserved through Unicode escapes, not renamed.

A repository text scan found no remaining Korean text in application source, scripts, tests, usage documents, or promotional HTML/JS/CSS. User data, installed dependencies, and historical screenshot pixels were excluded from translation. The promotional pages were already English and were not changed.

## Actual workflow and screenshots

```powershell
.\.build\qa\Scripts\python.exe -B scripts/qa_workspace.py --real-demucs --evidence-dir docs/qa/english
```

Selected original seconds 2–4 of a generated six-second WAV in the English UI. Real CPU Demucs produced four **2.000-second** stems, and all four individual exports were **2.000 seconds**. The final cached-model split took **23.985 seconds**. This verifies workflow/range behavior, not separation quality on music.

Result: [workflow-results.json](workflow-results.json).

Inspected actual test-window captures after deferred resize/redraw callbacks settled:

- [1280×720 workspace](captures/desktop-top.png)
- [900×600 workspace](captures/compact-top.png)
- [900×600 EQ and results](captures/compact-eq.png)
- [640×480 results](captures/small-results.png)
- [Export and Project Settings](captures/settings.png)

English labels fit the inspected controls. The existing vertical/horizontal scrolling behavior is retained for compact windows.

## English executable

- Launcher: Run KWAK Split.cmd at the repository root.
- Executable: release/english/KWAK Split/KWAK Split.exe.
- Build: PyInstaller 6.22.3, Python 3.11.9, staged first in .build/english-dist so the running previous release was untouched. Tools, models, runtime, notices, and documentation were then packaged in the separate English folder.
- Future builds: powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1.
- EXE --smoke-test: actual window initialization followed by automatic shutdown, **exit code 0**.
- SHA256: 909E51327E07F09D23D8E9F2BA51EEE422A75742D0DC47D78E162AC445A6F9AA.
- Copied preferences remained byte-identical to the previous release after the smoke test. Original temporary data, exports, logs, and the running window were left in place.
- The prior release remains at release/KWAK Split/. It is a preserved older version, not the current root-launcher target.

The copied Demucs virtual environment still references this PC's Python installation. Cross-PC standalone execution, physical display-scaling changes, direct OS mouse/keyboard use, and speaker listening are not claimed by these checks. No Git commit, push, or external publication was performed.
