#!/bin/bash

# build, upload, extract, and run cappsule on VM

set -e

# never called...
function usage()
{
	printf "Usage: $0 [options]\n"
	printf "\t-c,--clean\n"
	printf "\t-d,--dontrun\n"
	printf "\t-h,--host <ip>\n"
	printf "\t-m,--make\n"
	printf "\t-n,--nohv\n"
	exit 0
}

function parse_args()
{
	# http://www.bahmanm.com/blogs/command-line-options-how-to-parse-in-bash-using-getopt
	TEMP=$(getopt -o cdh:mn --long clean,dontrun,host:,make,nohv -n $(basename "$0") -- "$@")
	eval set -- "$TEMP"

	# default values
	CONFIG_NAME='default'
	NOHV=0
	MAKE=0
	CLEAN=0
	DONTRUN=0
	VM='vm.cappsule'

	while true ; do
		case "$1" in
			-c|--clean)
				CLEAN=1; shift 1;
				;;
			-d|--dontrun)
				DONTRUN=1; shift 1;
				;;
			-h|--host)
				case "$2" in
					"")	shift 2	;;
					*)	VM=$2; shift 2 ;;
				esac
				;;
			-m|--make)
				MAKE=1; shift 1;
				;;
			-n|--nohv)
				CONFIG_NAME='nohv'
				NOHV=1; shift 1;
				;;
			--)
				shift; break
				;;
			*)
				echo "Internal error!"; exit 1
				;;
		esac
	done
}

function build()
{
	if [ $CLEAN -ne 0 ]; then
		NOHV=0 make -C ../src clean
		NOHV=1 make -C ../src clean
	fi

	if [ $NOHV -eq 1 ]; then
		NOHV=1 make -C ../src/userland
	else
		make -C ../src/hv
		make -C ../src/userland
	fi
}

PACKAGE_NAME='cappsule.deb'
ARCHIVE_NAME='cappsule.tar.bz2'

DIR=$( dirname "$0" )
cd $DIR

parse_args $*

if [ $MAKE -ne 0 ]; then
	build
fi

# build debian package
./build_package.py --config ${CONFIG_NAME} --filename ${PACKAGE_NAME}

# upload package to VM
scp ${ARCHIVE_NAME} root@${VM}:
ssh root@${VM} tar --warning=no-timestamp -C / -xjf ${ARCHIVE_NAME}

# run daemon
if [ $DONTRUN -ne 1 ]; then
	ssh -t root@${VM} "/usr/local/cappsule/usr/bin/daemon --debug"
fi
