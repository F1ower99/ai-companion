[app]
title = AICompanion
project_dir = .
input_file = src/companion/desktop/app.py
exec_directory = dist
project_file =
icon =

[python]
python_path =
# Intentionally empty: the wrapper preflights installed tools, never installs.
packages =

[qt]
qml_files =
excluded_qml_plugins =
modules =
plugins =

[nuitka]
macos.permissions =
mode = standalone
extra_args = --msvc=latest --windows-console-mode=disable --noinclude-qt-translations --include-package=companion
