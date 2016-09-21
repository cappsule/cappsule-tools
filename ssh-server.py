#!/usr/bin/env python3

'''
Wait for TCP connections on EXTERNAL_PORT. Each connection is redirected to a
OpenSSH server running in a new capsule.
'''

import ctypes
import fcntl
import os
import re
import shutil
import signal
import socket
import socketserver
import subprocess
import sys
import tempfile
import time

EXTERNAL_PORT = 57575
VIRT_PATH     = '/usr/local/cappsule/usr/bin/virt'
POLICY        = 'unrestricted'
SSHD_PORT     = 2222
SSHD_HOST_KEY = os.path.expanduser('~/.ssh/ssh_host_rsa_key')
DIFF_DIRS     = os.path.expanduser('~/cappsule-diff-dirs/')


class Client:

    def __init__(self, request):
        self.fd = request
        self.libc = ctypes.cdll.LoadLibrary('libc.so.6')
        self.diff_dir = tempfile.mkdtemp(dir=DIFF_DIRS)

    def _debug(self, msg):
        print(msg)

    def _set_pdeath(self):
        PR_SET_PDEATHSIG = 1
        self.libc.prctl(PR_SET_PDEATHSIG, signal.SIGKILL)

    def _run_sshd(self):
        '''Run sshd in a new capsule.'''
        virt = [ VIRT_PATH, 'exec', '-n', '-p', POLICY, '--diffdir', self.diff_dir ]
        args = virt + [
            '/usr/sbin/sshd', '-D',
            '-f', '/dev/null',
            '-e',
            '-p', str(SSHD_PORT),
            '-o', 'HostKey={}'.format(SSHD_HOST_KEY),
            '-o', 'UseDNS=no',
            '-o', 'PasswordAuthentication=no',
        ]
        # set pdeath to ensure that capsule is killed when client instance exits
        return subprocess.Popen(args, preexec_fn=self._set_pdeath)

    def _find_capsule_id(self, target_pid):
        '''Find capsule id given virt's pid.'''

        for i in range(0, 50):
            output = subprocess.check_output([ VIRT_PATH, 'ps' ])
            pattern = '\#(?P<id>\d+)\s+(?P<user>\S+)\s+(?P<pid>\d+)\s+'
            it = re.finditer(pattern, str(output), re.MULTILINE)
            for match in it:
                capsule_id = int(match.group('id'))
                pid = int(match.group('pid'))
                if pid == target_pid:
                    return capsule_id
            time.sleep(0.1)

        return -1

    def _test_connection(self, ip, port):
        '''Return True if TCP connection succeeds.'''

        try:
            s = socket.create_connection((ip, port))
        except ConnectionRefusedError:
            return False
        except OSError:
            return False
        s.close()
        return True

    def _forward_connection(self, ip, port):
        args = [
            'socat',
            'FD:{}'.format(self.fd.fileno()),
            'TCP-CONNECT:{}:{}'.format(ip, port)
        ]

        old_flags = fcntl.fcntl(self.fd, fcntl.F_GETFD)
        fcntl.fcntl(self.fd, fcntl.F_SETFD, old_flags & (~fcntl.FD_CLOEXEC))
        subprocess.call(args, close_fds=False)

    def _remove_diff_dir(self):
        '''Unlink diff directories.'''

        dirs = [ self.diff_dir, self.diff_dir + '.workdir' ]
        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)

    def run_in_ssh(self):
        # run sshd in a new capsule
        sshd = self._run_sshd()

        # get capsule id
        capsule_id = self._find_capsule_id(sshd.pid)
        if capsule_id == -1:
            self._debug('fail to find capsule with pid %d' % sshd.pid)
            sys.exit(1)
        else:
            self._debug('capsule id: %d' % capsule_id)

        # wait for network to be ready
        ip = '172.17.0.{}'.format(capsule_id)
        port = SSHD_PORT
        network_ready = False
        for i in range(0, 50):
            if self._test_connection(ip, port):
                network_ready = True
                break
            time.sleep(0.1)

        if not network_ready:
            self._debug('failed to setup network of capsule %d' % capsule_id)
            sys.exit(1)

        # forward connection to encapsulated sshd
        self._forward_connection(ip, port)

        self._remove_diff_dir()


class TCPRequestHandler(socketserver.BaseRequestHandler):
    allow_reuse_address = True

    def handle(self):
        print("[*] new client: {}".format(self.client_address[0]))
        c = Client(self.request)
        c.run_in_ssh()


class ForkingTCPServer(socketserver.ForkingMixIn, socketserver.TCPServer):
    pass


if __name__ == '__main__':
    if not os.path.exists(DIFF_DIRS):
        os.makedirs(DIFF_DIRS, mode=0o755)

    socketserver.TCPServer.allow_reuse_address = True
    server = ForkingTCPServer(('0.0.0.0', EXTERNAL_PORT), TCPRequestHandler)
    server.serve_forever()
