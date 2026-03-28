#!/usr/bin/env bash

set -euo pipefail

usage() {
    printf 'Usage: %s [--dry-run] [<region> ...]\n' "$0" >&2
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

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run)
            dry_run=1
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

is_image_name() {
    case "${1,,}" in
        *.png|*.jpg|*.jpeg|*.webp|*.gif|*.bmp|*.tif|*.tiff)
            return 0
            ;;
    esac
    return 1
}

link_one() {
    local source_path=$1
    local target_path=$2

    if [ -e "$target_path" ] && [ "$target_path" -ef "$source_path" ]; then
        printf 'skip\t%s\n' "$target_path"
        return 0
    fi

    if [ "$dry_run" -eq 1 ]; then
        if [ -e "$target_path" ]; then
            printf 'would_replace\t%s\t%s\n' "$source_path" "$target_path"
        else
            printf 'would_link\t%s\t%s\n' "$source_path" "$target_path"
        fi
        return 0
    fi

    mkdir -p -- "$(dirname -- "$target_path")"
    rm -f -- "$target_path"
    ln -- "$source_path" "$target_path"
    printf 'linked\t%s\t%s\n' "$source_path" "$target_path"
}

prune_stale_files() {
    local pictures_dir=$1
    local keep_files=$2

    if [ ! -d "$pictures_dir" ]; then
        return 0
    fi

    while IFS= read -r existing_path; do
        local relative_path
        relative_path=${existing_path#"$pictures_dir"/}
        if grep -Fqx -- "$relative_path" "$keep_files"; then
            continue
        fi

        if [ "$dry_run" -eq 1 ]; then
            printf 'would_remove\t%s\n' "$existing_path"
            continue
        fi

        rm -f -- "$existing_path"
        printf 'removed\t%s\n' "$existing_path"
    done < <(find "$pictures_dir" -mindepth 2 -maxdepth 2 -type f | sort)
}

prune_stale_dirs() {
    local pictures_dir=$1
    local keep_dirs=$2

    if [ ! -d "$pictures_dir" ]; then
        return 0
    fi

    while IFS= read -r existing_dir; do
        local base_name
        base_name=$(basename -- "$existing_dir")
        if grep -Fqx -- "$base_name" "$keep_dirs"; then
            continue
        fi

        if [ "$dry_run" -eq 1 ]; then
            printf 'would_remove_dir\t%s\n' "$existing_dir"
            continue
        fi

        rm -rf -- "$existing_dir"
        printf 'removed_dir\t%s\n' "$existing_dir"
    done < <(find "$pictures_dir" -mindepth 1 -maxdepth 1 -type d | sort)
}

for region_dir in "${regions[@]}"; do
    pictures_dir=$region_dir/pictures
    keep_dirs=$(mktemp)
    keep_files=$(mktemp)

    while IFS= read -r -d '' team_dir; do
        team_name=$(basename -- "$team_dir")
        case "$team_name" in
            emails|pictures)
                continue
                ;;
            *-*)
                ;;
            *)
                continue
                ;;
        esac

        while IFS= read -r -d '' part_dir; do
            part_name=$(basename -- "$part_dir")
            collapsed_dir_name=$team_name-$part_name
            found_image=0

            while IFS= read -r -d '' image_path; do
                image_name=$(basename -- "$image_path")
                if ! is_image_name "$image_name"; then
                    continue
                fi

                found_image=1
                printf '%s\n' "$collapsed_dir_name" >>"$keep_dirs"
                printf '%s/%s\n' "$collapsed_dir_name" "$image_name" >>"$keep_files"
                link_one "$image_path" "$pictures_dir/$collapsed_dir_name/$image_name"
            done < <(find "$part_dir" -mindepth 1 -maxdepth 1 -type f -print0 | sort -z)

            if [ "$found_image" -eq 0 ]; then
                continue
            fi
        done < <(find "$team_dir" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)
    done < <(find "$region_dir" -mindepth 1 -maxdepth 1 -type d -print0 | sort -z)

    prune_stale_files "$pictures_dir" "$keep_files"
    prune_stale_dirs "$pictures_dir" "$keep_dirs"
    rm -f -- "$keep_dirs" "$keep_files"
done
