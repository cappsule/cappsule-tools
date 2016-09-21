#!/usr/bin/env python

'''
Build cappsule's debian package.
'''

import argparse
import ConfigParser
import hashlib
import tarfile
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile


LIGHTDM_CONF = '[SeatDefaults]\nxserver-command=%sX-wrapper-qubes\n'
SYSTEMD_CONF = '[Unit]\nDescription=Job that runs the cappsule daemon\n\n[Service]\nType=forking\nExecStart=%s\n\n[Install]\nWantedBy=graphical.target\n'
XORG_WRAP = '#!/bin/sh\n\nexec %s $@\n'
DEBIAN = {
    'control': '''Source: cappsule
Version: 1.0
Section: admin
Priority: extra
Maintainer: Gabriel Campana <gcampana+cappsule@quarkslab.com>
Package: cappsule
Architecture: amd64
Installed-Size: %d
Depends: %s
Description: Lightweight hypervisor
 Encapsulate userland process transparently.
''',

    'postinst': '''#!/bin/sh

set -e

if [ "$1" = configure ]; then
    mkdir -p -m 0775 /var/log/cappsule/
    if [ $(getent group syslog) ]; then
        chown root:syslog /var/log/cappsule/
    fi
fi

systemctl enable cappsule
'''
}


class Deb:
    BUILD_DIR = tempfile.mkdtemp()
    SRC_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), '..')

    def __init__(self, config_name):
        self._md5sums = {}
        self._conffiles = []
        self._installed_size = 0
        self._config_name = config_name


    def _ask(self, msg):
        sys.stdout.write(msg)
        choice = raw_input().lower()
        if choice in [ 'yes', 'y', 'ye', '' ]:
            return True
        else:
            print '[-] aborting'
            sys.exit(0)


    def _copy_with_perms(self, src, dst, verbose=False):
        if verbose:
            print src, dst

        if not os.path.exists(src):
            print "[-] %s doesn't exist" % src
            sys.exit(1)
        st = os.stat(src)
        shutil.copyfile(src, dst)
        os.chmod(dst, st.st_mode)


    def _write_debian_files(self):
        debian_path = os.path.join(self.BUILD_DIR, 'DEBIAN')
        os.makedirs(debian_path, 0755)

        for name, content in DEBIAN.iteritems():
            path = os.path.join(debian_path, name)
            # fix Installed-Size and Depends
            if name == 'control':
                content = content % (self._installed_size / 1024 + 1, DEPENDS)
            with open(path, 'w') as fp:
                fp.write(content)
            if name in [ 'preinst', 'postinst', 'prerm', 'postrm' ]:
                os.chmod(path, 0755)

        path = os.path.join(debian_path, 'md5sums')
        md5sums = [ '%s  %s' % (m, n) for n, m in self._md5sums.iteritems() ]
        md5sums = '\n'.join(md5sums) + '\n'
        with open(path, 'w') as fp:
            fp.write(md5sums)
        os.chmod(path, 0644)

        path = os.path.join(debian_path, 'conffiles')
        conffiles = [ os.path.join('/', c) for c in self._conffiles ]
        conffiles = '\n'.join(conffiles) + '\n'
        with open(path, 'w') as fp:
            fp.write(conffiles)
        os.chmod(path, 0644)


    def _create_dynamic_files(self):
        tmpfiles = []
        files = {
            'lib/systemd/system/cappsule.service': (SYSTEMD_CONF, 0644),
            'usr/lib/xorg/Xorg.wrap': (XORG_WRAP, 0755),
        }

        # don't include lightdm configuration file in server release
        if self._config_name != 'server':
            files['etc/lightdm/lightdm.conf.d/cappsule.conf'] = (LIGHTDM_CONF, 0644)

        for dst, (data, mode) in files.iteritems():
            fd, path = tempfile.mkstemp()
            os.chmod(path, mode)
            with os.fdopen(fd, 'w') as fp:
                fp.write(data)
            FILES[path] = dst
            self._conffiles.append(FILES[path])
            tmpfiles.append(path)

        return tmpfiles


    def build(self):
        tmpfiles = self._create_dynamic_files()

        for src, dst in FILES.iteritems():
            if not src.startswith('/'):
                if src.startswith('conf/') or src.startswith('policies/'):
                    self._conffiles.append(dst)
                    src = os.path.join('tools/', src)
                src = os.path.join(self.SRC_DIR, src)

            if not os.path.exists(src):
                print '[-] file "%s" is missing, aborting.' % src
                sys.exit(1)

            with open(src) as fp:
                self._md5sums[dst] = hashlib.md5(fp.read()).hexdigest()

            self._installed_size += os.stat(src).st_size

            dst = os.path.join(self.BUILD_DIR, dst)
            dirname, _ = os.path.split(dst)
            if not os.path.exists(dirname):
                os.makedirs(dirname, 0755)

            self._copy_with_perms(src, dst, False)

        for path in tmpfiles:
            os.unlink(path)

        self._write_debian_files()


    def write_deb(self, name):
        argv = [
            '/usr/bin/fakeroot',
            'dpkg-deb', '--build', self.BUILD_DIR, name
        ]
        subprocess.call(argv)


    def write_tar(self, name):
        name = os.path.splitext(name)[0] + '.tar.bz2'
        argv = [
            'tar',
            '-C', self.BUILD_DIR,
            '--exclude=./DEBIAN',
            '--owner=0', '--group=0',
            '-cjf', name,
            'etc/', 'usr/', 'lib/'
        ]
        subprocess.call(argv)


    def remove_build_dir(self):
        shutil.rmtree(self.BUILD_DIR)


def fix_config_files(flavour):
    global LIGHTDM_CONF, SYSTEMD_CONF, XORG_WRAP

    bin_path = os.path.join('/', PATHS['BINARY'])

    LIGHTDM_CONF = LIGHTDM_CONF % bin_path

    filename = {
        'default': 'daemon',
        'server': 'daemon',
    }[flavour]
    filename = os.path.join('/', PATHS['BINARY'], filename)
    SYSTEMD_CONF = SYSTEMD_CONF % filename
    XORG_WRAP = XORG_WRAP % os.path.join('/', PATHS['BINARY'], 'X-wrapper-qubes')


def parse_config(flavour):
    global INSTALL_PREFIX, PATHS, FILES, DEPENDS

    flavour_file = {
        'default': 'default.conf',
        'server': 'server.conf',
    }[flavour]

    script_dir = os.path.dirname(os.path.realpath(__file__))
    flavour_files = [ 'common.conf', flavour_file ]
    flavour_files = [ os.path.join(script_dir, 'flavour/', f) for f in flavour_files ]

    config = ConfigParser.ConfigParser()
    config.optionxform = str # make option names case sensitive
    config.read(flavour_files)

    INSTALL_PREFIX = config.get('Global', 'INSTALL_PREFIX')

    PATHS = {}
    for k, v in config.items('Paths'):
        if k != 'RSYSLOG':
            v = os.path.join(INSTALL_PREFIX, v)
        PATHS[k.upper()] = v

    FILES = dict(config.items('Files'))
    for k, v in FILES.iteritems():
        if '/' in v:
            v, filename = v.split('/', 1)
        else:
            v, filename = (v, os.path.basename(k))
        FILES[k] = os.path.join(PATHS[v], filename)

    DEPENDS = config.get('Debian', 'Depends')
    DEPENDS = ', '.join(re.sub('\s+', '', DEPENDS).split(','))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', help='configuration name',
                        action='store',
                        choices=['default', 'server'],
                        default='default')
    parser.add_argument('-f', '--filename', help='.deb filename',
                        action='store',
                        default='cappsule.deb')

    args = parser.parse_args()

    flavour = args.config
    filename = args.filename

    print '[*] building package "%s" with config "%s"' % (filename, flavour)

    parse_config(flavour)
    fix_config_files(flavour)

    d = Deb(flavour)
    d.build()
    d.write_deb(filename)
    d.write_tar(filename)
    d.remove_build_dir()
