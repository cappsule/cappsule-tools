#!/bin/bash

DIR=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )

binaries="daemon/daemon
snapshot/snapshot
devices/gui/agent-linux/guiclient
devices/gui/daemon/guiserver
devices/fs/fsserver
devices/fs/fsclient
logger/logger
devices/console/consoleserver
devices/net/netclient
devices/net/netserver"

for relpath in $binaries; do
    path="$DIR/../src/userland/$relpath"
    if [ -f "$path" ]; then
		hardening-check --color "$path"
		echo ''
    fi
done
