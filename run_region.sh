#!/usr/bin/env bash

set -euo pipefail

usage() {
    printf 'Usage: %s [-v] <region>\n' "$0" >&2
}

die_usage() {
    usage
    exit 1
}

script_dir=$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
    pwd -P
)
self_path=$script_dir/$(basename -- "${BASH_SOURCE[0]}")
python_bin=${PYTHON:-python3}
blender_bin=${BLENDER:-blender}

run_with_optional_filter() {
    local verbose=$1
    shift

    if [ "$verbose" -eq 1 ]; then
        exec "$@"
    fi

    local stdout_file
    stdout_file=$(mktemp)

    if "$@" >"$stdout_file"; then
        awk 'index($0, "skip\t") != 1 { print }' "$stdout_file"
        rm -f -- "$stdout_file"
        return 0
    fi

    local status=$?
    cat "$stdout_file" >&2
    rm -f -- "$stdout_file"
    return "$status"
}

run_clean_one() {
    local verbose=$1
    local stl_path=$2
    run_with_optional_filter "$verbose" "$script_dir/clean_hubspot_dl_names.sh" "$stl_path"
}

run_render_one() {
    local verbose=$1
    local team_dir=$2
    run_with_optional_filter \
        "$verbose" \
        "$blender_bin" \
        --background \
        --python \
        "$script_dir/render.py" \
        -- \
        "$team_dir"
}

run_compose_one() {
    local verbose=$1
    local team_dir=$2
    run_with_optional_filter "$verbose" "$python_bin" "$script_dir/compose.py" "$team_dir"
}

dispatch_internal() {
    local mode=$1
    shift

    local verbose=0
    if [ "${1:-}" = "--verbose" ]; then
        verbose=1
        shift
    fi

    if [ "$#" -ne 1 ]; then
        die_usage
    fi

    case "$mode" in
        --clean-one)
            run_clean_one "$verbose" "$1"
            ;;
        --render-one)
            run_render_one "$verbose" "$1"
            ;;
        --compose-one)
            run_compose_one "$verbose" "$1"
            ;;
        *)
            die_usage
            ;;
    esac
}

if [ "${1:-}" = "--clean-one" ] || [ "${1:-}" = "--render-one" ] || [ "${1:-}" = "--compose-one" ]; then
    dispatch_internal "$@"
    exit $?
fi

verbose=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        -v|--verbose)
            verbose=1
            shift
            ;;
        --help)
            usage
            exit 0
            ;;
        --)
            shift
            break
            ;;
        -*)
            die_usage
            ;;
        *)
            break
            ;;
    esac
done

if [ "$#" -ne 1 ]; then
    die_usage
fi

if ! region_dir=$(
    cd -- "$1"
    pwd -P
); then
    printf 'missing region\t%s\n' "$1" >&2
    exit 1
fi

verbose_arg=()
if [ "$verbose" -eq 1 ]; then
    verbose_arg=(--verbose)
    printf 'cleaning\t%s\n' "$region_dir"
fi

(
    cd -- "$region_dir"
    fd -e stl -x "$self_path" --clean-one "${verbose_arg[@]}" {}
)

if [ "$verbose" -eq 1 ]; then
    printf 'rendering\t%s\n' "$region_dir"
fi

(
    cd -- "$region_dir"
    fd -td -d 1 . -x "$self_path" --render-one "${verbose_arg[@]}" {}
)

if [ "$verbose" -eq 1 ]; then
    printf 'composing\t%s\n' "$region_dir"
fi

(
    cd -- "$region_dir"
    fd -td -d 1 . -x "$self_path" --compose-one "${verbose_arg[@]}" {}
)
