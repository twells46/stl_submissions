#!/usr/bin/env bash

set -euo pipefail

usage() {
    printf 'Usage: %s [--dry-run] [--force] [<region> ...]\n' "$0" >&2
}

die_usage() {
    usage
    exit 1
}

script_dir=$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
    pwd -P
)

dry_run=0
force=0

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run)
            dry_run=1
            shift
            ;;
        --force)
            force=1
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

regions=()
if [ "$#" -gt 0 ]; then
    for region in "$@"; do
        if ! region_dir=$(
            cd -- "$region"
            pwd -P
        ); then
            printf 'missing_region\t%s\n' "$region" >&2
            exit 1
        fi
        regions+=("$region_dir")
    done
else
    while IFS= read -r region_dir; do
        regions+=("$region_dir")
    done < <(
        find "$script_dir" -mindepth 1 -maxdepth 1 -type d ! -name '.*' ! -name '__pycache__' | sort
    )
fi

link_one() {
    local source_path=$1
    local target_path=$2

    if [ -e "$target_path" ]; then
        if [ "$force" -ne 1 ] && [ "$target_path" -ef "$source_path" ]; then
            printf 'skip\t%s\n' "$target_path"
            return 0
        fi

        if [ "$dry_run" -eq 1 ]; then
            printf 'would_replace\t%s\t%s\n' "$source_path" "$target_path"
            return 0
        fi

        rm -f -- "$target_path"
        ln -- "$source_path" "$target_path"
        printf 'relinked\t%s\t%s\n' "$source_path" "$target_path"
        return 0
    fi

    if [ "$dry_run" -eq 1 ]; then
        printf 'would_link\t%s\t%s\n' "$source_path" "$target_path"
        return 0
    fi

    ln -- "$source_path" "$target_path"
    printf 'linked\t%s\t%s\n' "$source_path" "$target_path"
}

prune_stale_links() {
    local emails_dir=$1
    local keep_file=$2

    if [ ! -d "$emails_dir" ]; then
        return 0
    fi

    while IFS= read -r existing_path; do
        local base_name
        base_name=$(basename -- "$existing_path")
        if grep -Fqx -- "$base_name" "$keep_file"; then
            continue
        fi

        if [ "$dry_run" -eq 1 ]; then
            printf 'would_remove\t%s\n' "$existing_path"
            continue
        fi

        rm -f -- "$existing_path"
        printf 'removed\t%s\n' "$existing_path"
    done < <(find "$emails_dir" -mindepth 1 -maxdepth 1 -type f -name '*.eml' | sort)
}

for region_dir in "${regions[@]}"; do
    emails_dir=$region_dir/emails
    keep_file=$(mktemp)

    while IFS= read -r source_path; do
        relative_path=${source_path#"$region_dir"/}
        if [ "$relative_path" = "$source_path" ]; then
            printf 'unexpected_path\t%s\n' "$source_path" >&2
            rm -f -- "$keep_file"
            exit 1
        fi

        file_name=${relative_path//\//--}
        target_path=$emails_dir/$file_name
        printf '%s\n' "$file_name" >>"$keep_file"

        if [ "$dry_run" -eq 0 ]; then
            mkdir -p -- "$emails_dir"
        fi

        link_one "$source_path" "$target_path"
    done < <(
        find "$region_dir" \
            -path "$emails_dir" -prune -o \
            -type f -name '*.eml' -print | sort
    )

    prune_stale_links "$emails_dir" "$keep_file"
    rm -f -- "$keep_file"
done
