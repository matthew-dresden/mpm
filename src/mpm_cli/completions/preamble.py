"""Shell completion preamble for shtab integration.

This module exports PREAMBLE, a dict mapping shell names to preamble
script fragments that shtab prepends to the generated completion script.

The bash and zsh entries define mpm-specific shell helper functions for
dynamic argument completion. Each helper shells out to the corresponding
``mpm __complete_<name>`` subcommand to retrieve candidate lists.

Environment variables honoured by every helper:

- ``MPM_COMPLETION_ENABLED`` (default: ``1``) -- when set to ``0``, the
  helper returns the empty candidate list immediately without invoking the
  mpm subprocess.
- ``MPM_COMPLETION_TIMEOUT`` (default: ``2``) -- number of seconds passed
  to ``timeout``(1) wrapping the mpm subprocess call. When ``timeout``(1)
  is not on ``$PATH``, the subprocess relies on mpm's own internal timeout
  (also bounded by this variable).

The mid-token splitter helper (``_mpm_complete_add_arg``) detects the ``@``
separator in the current completion token, splits on the LAST ``@`` (spec
Section 4.0 LAST-``@`` split rule), and routes to the appropriate completer:

- No ``@`` in token: delegates to ``_mpm_complete_catalog_entries``.
- ``@`` present: shells out to ``mpm __resolve_entry_to_repo_url <name>``
  to get the repo URL for the entry to the left of the last ``@``, then
  delegates to ``_mpm_complete_project_versions <repo_url> <spec>``.
"""

from __future__ import annotations


_BASH_PREAMBLE = r"""
# mpm shell-completion preamble (bash)
# Sourced by the generated completion script produced by `mpm completion bash`.

# _mpm_run_complete <subcommand> [args...]
#
# Common dispatcher called by every named helper.
# Respects MPM_COMPLETION_ENABLED and MPM_COMPLETION_TIMEOUT.
_mpm_run_complete() {
    local _subcommand="$1"
    shift
    # Honour MPM_COMPLETION_ENABLED (default 1 = enabled).
    if [[ "${MPM_COMPLETION_ENABLED:-1}" == "0" ]]; then
        COMPREPLY=()
        return 0
    fi
    local _timeout="${MPM_COMPLETION_TIMEOUT:-2}"
    local _output
    if command -v timeout > /dev/null 2>&1; then
        _output=$(timeout "$_timeout" mpm "$_subcommand" "$@" 2>/dev/null) || true
    else
        _output=$(mpm "$_subcommand" "$@" 2>/dev/null) || true
    fi
    mapfile -t COMPREPLY < <(compgen -W "$_output" -- "${cur:-}")
}

_mpm_complete_catalog_entries() {
    local cur="${1:-}"
    _mpm_run_complete __complete_catalog_entries "$cur"
}

_mpm_complete_source_names_in_mpm() {
    local cur="${1:-}"
    _mpm_run_complete __complete_source_names_in_mpm "$cur"
}

_mpm_complete_names_in_lockfile() {
    local cur="${1:-}"
    _mpm_run_complete __complete_names_in_lockfile "$cur"
}

_mpm_complete_catalog_versions() {
    local cur="${1:-}"
    _mpm_run_complete __complete_catalog_versions "$cur"
}

_mpm_complete_project_versions() {
    local repo_url="${1:-}"
    local cur="${2:-}"
    _mpm_run_complete __complete_project_versions "$repo_url" "$cur"
}

_mpm_complete_cached_catalogs() {
    local cur="${1:-}"
    _mpm_run_complete __complete_cached_catalogs "$cur"
}

# _mpm_complete_add_arg -- mid-token splitter helper.
#
# Implements spec Section 11.5: detects the @ separator and routes to the
# appropriate completer. Splits on the LAST @ (spec Section 4.0).
#
# When MPM_COMPLETION_ENABLED=0, returns immediately with empty COMPREPLY
# without shelling out to mpm __resolve_entry_to_repo_url.
_mpm_complete_add_arg() {
    local cur="${1:-}"
    # Honour MPM_COMPLETION_ENABLED (default 1 = enabled).
    if [[ "${MPM_COMPLETION_ENABLED:-1}" == "0" ]]; then
        COMPREPLY=()
        return 0
    fi
    if [[ "$cur" == *@* ]]; then
        # Split on the LAST @ per spec Section 4.0.
        local _name="${cur%@*}"
        local _spec="${cur##*@}"
        local _repo_url
        local _timeout="${MPM_COMPLETION_TIMEOUT:-2}"
        if command -v timeout > /dev/null 2>&1; then
            _repo_url=$(timeout "$_timeout" mpm __resolve_entry_to_repo_url "$_name" 2>/dev/null) || return 0
        else
            _repo_url=$(mpm __resolve_entry_to_repo_url "$_name" 2>/dev/null) || return 0
        fi
        [[ -z "$_repo_url" ]] && return 0
        _mpm_complete_project_versions "$_repo_url" "$_spec"
    else
        _mpm_complete_catalog_entries "$cur"
    fi
}
"""


_ZSH_PREAMBLE = r"""
# mpm shell-completion preamble (zsh)
# Sourced by the generated completion script produced by `mpm completion zsh`.

# _mpm_run_complete <subcommand> [args...]
#
# Common dispatcher called by every named helper.
# Respects MPM_COMPLETION_ENABLED and MPM_COMPLETION_TIMEOUT.
_mpm_run_complete() {
    local _subcommand="$1"
    shift
    # Honour MPM_COMPLETION_ENABLED (default 1 = enabled).
    if [[ "${MPM_COMPLETION_ENABLED:-1}" == "0" ]]; then
        return 0
    fi
    local _timeout="${MPM_COMPLETION_TIMEOUT:-2}"
    local -a _lines
    if command -v timeout > /dev/null 2>&1; then
        _lines=("${(@f)$(timeout "$_timeout" mpm "$_subcommand" "$@" 2>/dev/null)}")
    else
        _lines=("${(@f)$(mpm "$_subcommand" "$@" 2>/dev/null)}")
    fi
    # Filter empty lines that result from trailing newlines in subprocess output.
    local -a _candidates
    local _item
    for _item in "${_lines[@]}"; do
        [[ -n "$_item" ]] && _candidates+=("$_item")
    done
    [[ ${#_candidates[@]} -gt 0 ]] && compadd -- "${_candidates[@]}"
}

_mpm_complete_catalog_entries() {
    local cur="${1:-}"
    _mpm_run_complete __complete_catalog_entries "$cur"
}

_mpm_complete_source_names_in_mpm() {
    local cur="${1:-}"
    _mpm_run_complete __complete_source_names_in_mpm "$cur"
}

_mpm_complete_names_in_lockfile() {
    local cur="${1:-}"
    _mpm_run_complete __complete_names_in_lockfile "$cur"
}

_mpm_complete_catalog_versions() {
    local cur="${1:-}"
    _mpm_run_complete __complete_catalog_versions "$cur"
}

_mpm_complete_project_versions() {
    local repo_url="${1:-}"
    local cur="${2:-}"
    _mpm_run_complete __complete_project_versions "$repo_url" "$cur"
}

_mpm_complete_cached_catalogs() {
    local cur="${1:-}"
    _mpm_run_complete __complete_cached_catalogs "$cur"
}

# _mpm_complete_add_arg -- mid-token splitter helper.
#
# Implements spec Section 11.5: detects the @ separator and routes to the
# appropriate completer. Splits on the LAST @ (spec Section 4.0).
#
# When MPM_COMPLETION_ENABLED=0, returns immediately without shelling out
# to mpm __resolve_entry_to_repo_url.
_mpm_complete_add_arg() {
    local cur="${1:-}"
    # Honour MPM_COMPLETION_ENABLED (default 1 = enabled).
    if [[ "${MPM_COMPLETION_ENABLED:-1}" == "0" ]]; then
        return 0
    fi
    if [[ "$cur" == *@* ]]; then
        # Split on the LAST @ per spec Section 4.0.
        local _name="${cur%@*}"
        local _spec="${cur##*@}"
        local _repo_url
        local _timeout="${MPM_COMPLETION_TIMEOUT:-2}"
        if command -v timeout > /dev/null 2>&1; then
            _repo_url=$(timeout "$_timeout" mpm __resolve_entry_to_repo_url "$_name" 2>/dev/null) || return 0
        else
            _repo_url=$(mpm __resolve_entry_to_repo_url "$_name" 2>/dev/null) || return 0
        fi
        [[ -z "$_repo_url" ]] && return 0
        _mpm_complete_project_versions "$_repo_url" "$_spec"
    else
        _mpm_complete_catalog_entries "$cur"
    fi
}
"""

PREAMBLE: dict[str, str] = {
    "bash": _BASH_PREAMBLE,
    "zsh": _ZSH_PREAMBLE,
}
