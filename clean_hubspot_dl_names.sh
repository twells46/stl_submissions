#!/usr/bin/env bash

set -eu

usage() {
    printf 'Usage: %s [--dry-run] [--force] <file>\n' "$0" >&2
}

die_usage() {
    usage
    exit 1
}

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

if [ "$#" -ne 1 ]; then
    die_usage
fi

fname=$1

if [ ! -f "$fname" ]; then
    printf 'missing\t%s\n' "$fname" >&2
    exit 1
fi

dir_name=$(dirname -- "$fname")
base_name=$(basename -- "$fname")

case "$base_name" in
    *-stl_file-*.stl)
        part_name=${base_name##*-stl_file-}
        part_name=${part_name%-*.stl}
        ;;
    *.stl)
        part_name=${base_name%.stl}
        ;;
    *)
        printf 'unsupported\t%s\n' "$fname" >&2
        exit 1
        ;;
esac

part_name=${part_name// /_}.stl
target_path=$dir_name/$part_name
current_path=$dir_name/$base_name

if [ "$target_path" = "$current_path" ]; then
    printf 'skip\t%s\n' "$fname"
    exit 0
fi

if [ -e "$target_path" ] && [ "$force" -ne 1 ]; then
    printf 'conflict\t%s\t%s\n' "$fname" "$target_path" >&2
    exit 1
fi

if [ "$dry_run" -eq 1 ]; then
    printf 'would_rename\t%s\t%s\n' "$fname" "$target_path"
    exit 0
fi

if [ "$force" -eq 1 ]; then
    mv -f -- "$fname" "$target_path"
else
    mv -- "$fname" "$target_path"
fi

printf 'renamed\t%s\t%s\n' "$fname" "$target_path"
