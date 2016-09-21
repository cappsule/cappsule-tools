#!/bin/bash

# List GPL symbols from a Linux kernel module.
# $ grep -r '^EXPORT_SYMBOL' . > /run/shm/export_symbols.txt

set -e

DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

get_symbols()
{
	local filename="$1"

	objdump --syms "$filename" | grep UND | awk '{ print $4 }'
}

list_gpl_symbols()
{
	local symbols="$@"
	local regexp='EXPORT_SYMBOL_GPL\(('
	regexp+=$(echo $symbols | tr ' ' '|')
	regexp+=')\)'

	egrep --no-filename "$regexp" /run/shm/export_symbols.txt \
		| cut -d ':' -f 2- \
		| sort -u
}

list_unknown_symbols()
{
	local symbols="$@"
	local regexp='EXPORT_SYMBOL(_GPL)?\(('
	regexp+=$(echo $symbols | tr ' ' '|')
	regexp+=')\)'

	local known=$( \
		egrep --no-filename "$regexp" /run/shm/export_symbols.txt \
		| cut -d ':' -f 2- \
		| sort -u
	)

	for sym in $symbols; do
		echo $known | egrep -q "EXPORT_SYMBOL(_GPL)?\($sym\)" || echo "UNKNOWN($sym)"
	done \
		| sort -u

}

main()
{
	local objfile="$DIR/../src/hv/cappsule.ko"
	local symbols=$(get_symbols "$objfile")

	list_gpl_symbols "$symbols"
	echo ''
	list_unknown_symbols "$symbols"
}

main
