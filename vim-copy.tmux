#!/usr/bin/env bash
# TPM entry point; compatible with the Bash 3.2 shipped with macOS.
set -eu

source_path=${BASH_SOURCE[0]}
while [ -L "$source_path" ]; do
  source_dir=$(CDPATH='' cd -P -- "$(dirname -- "$source_path")" && pwd)
  source_path=$(readlink "$source_path")
  case "$source_path" in
    /*) ;;
    *) source_path=$source_dir/$source_path ;;
  esac
done
plugin_dir=$(CDPATH='' cd -P -- "$(dirname -- "$source_path")" && pwd)

python=${TMUX_VIM_COPY_PYTHON:-}
if [ -z "$python" ]; then
  python=$(tmux show-option -gqv @vim-copy-python 2>/dev/null || :)
fi
python=${python:-python3}

if ! command -v "$python" >/dev/null 2>&1; then
  printf 'tmux-vim-copy: Python executable not found: %s\n' "$python" >&2
  printf 'Install Python 3.9+ or set TMUX_VIM_COPY_PYTHON (or tmux @vim-copy-python) to its executable path, without arguments.\n' >&2
  exit 127
fi

# Keep TMUX and its socket context intact for the installer and later bindings.
exec "$python" "$plugin_dir/vim_copy.py" install
