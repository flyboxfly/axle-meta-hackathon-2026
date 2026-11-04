"""Isolated SIGINT shutdown regression tests. Invented credentials only.

The child builds a real opening host with a temporary database and mocked
outbound HTTP that fails on any request, then runs the real
`pilot_launch.serve_host` shutdown path with a stub server (no sockets are
bound; this sandbox forbids bind). The parent delivers SIGINT to the child
only and asserts graceful exit 0 with a completed drain.
POSIX-only: precise per-process signal delivery is required.
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

CHILD = '''
import asyncio
import os
import tempfile
import httpx
import axle_hackathon.pilot_factory as factory
import axle_hackathon.pilot_launch as launch
from axle_hackathon.pilot_memory import MemoryPolicy

tmp = tempfile.mkdtemp(prefix='opening-shutdown-test-')

def handle(request):
    raise AssertionError('unexpected outbound request ' + str(request.url))

httpx.HTTPTransport = lambda **kw: httpx.MockTransport(handle)

class StubServer:
    def __init__(self, config):
        self.started = False
        self.should_exit = False
    async def serve(self):
        self.started = True
        print('SERVING', flush=True)
        while not self.should_exit:
            await asyncio.sleep(0.1)
launch.PrivateServer = StubServer

host = factory.build_opening_host(os.path.join(tmp, 'probe.sqlite3'), {(1, 1): 'owner'},
    MemoryPolicy(version='test', processing_notice='Invented shutdown test'),
    provider_key='invented', bot_token='123:' + 'x' * 30,
    webhook_secret='s' * 40, allowed_host='testserver',
    global_limit=4, carrier_limit=4)
host.owner.start()
asyncio.run(launch.serve_host(host))
print('SHUTDOWN ok', flush=True)
'''


def launch_child():
    env = dict(os.environ, PYTHONPATH=str(REPO / 'src'))
    return subprocess.Popen([sys.executable, '-c', CHILD], cwd=str(REPO), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)


def wait_serving(proc, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            _, err = proc.communicate(timeout=10)
            raise AssertionError('child exited %s before serving: %s' % (proc.returncode, err[-500:]))
        line = proc.stdout.readline()
        if line.strip() == 'SERVING':
            return
    raise AssertionError('timed out waiting for child to serve')


@pytest.mark.skipif(os.name != 'posix', reason='POSIX signals required')
@pytest.mark.parametrize('extra_signals', [0, 2])
def test_sigint_shutdown_is_graceful(extra_signals):
    proc = launch_child()
    try:
        wait_serving(proc)
        proc.send_signal(signal.SIGINT)
        for _ in range(extra_signals):
            time.sleep(0.5)
            if proc.poll() is None:
                proc.send_signal(signal.SIGINT)
        try:
            code = proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            raise AssertionError('child still running after SIGINT')
        out, err = proc.communicate(timeout=10)
        assert code == 0, err[-500:]
        assert 'SHUTDOWN ok' in out
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)
