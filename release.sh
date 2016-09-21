#!/bin/bash

# Build a release version package of Cappsule.

set -e

DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

if [ $# -eq 1 ] && [ "x$1" = 'x--server' ]; then
	config='server'
	filename="${DIR}/build/cappsule-server-$(date '+%y%m%d-%H%M')"
else
	config='default'
	filename="${DIR}/build/cappsule-$(date '+%y%m%d-%H%M')"
fi

# make kernel module
for target in clean all; do
	#RELEASE=1
	make -C "${DIR}/../src/hv" "$target"
done
#"${DIR}/../src/hv/scripts/obf.sh" "${DIR}/../src/hv/cappsule.ko" "$filename.ko.map"
#"${DIR}/../src/hv/scripts/obf.sh" "${DIR}/../src/hv/cappsule-guest.ko" "$filename.ko.guest.map"

# make userland
for target in clean all; do
	#RELEASE=1
	make -C "${DIR}/../src/userland" "$target"
done

# generate deb and tar.bz2 files
deb="$filename.deb"
tar="$filename.tar.bz2"
"${DIR}/build_package.py" --config "$config" --filename "$deb"
ls -lh "$deb" "$tar"

# produce a signature for each file
for f in "$deb" "$tar"; do
	gpg2 --armor --local-user 'cappsule@quarkslab.com' --output "$f.sig" --detach-sig "$f"
done
