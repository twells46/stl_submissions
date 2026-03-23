#!/bin/sh

if [ "$#" -ne "1" ]; then
    printf "Incorrect args\n"
    exit 1
fi

fname="${1}"
part_name="${1##*-stl_file-}"
part_name="${part_name%-*.stl}"
part_name="${part_name// /_}.stl"


#printf "$fname, $part_name\n"

mv "${fname}" "${part_name}"
