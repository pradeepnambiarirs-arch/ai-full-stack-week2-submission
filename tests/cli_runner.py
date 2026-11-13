"""Run CLI subprocess tests with network entry points denied in the child too."""
from contextlib import ExitStack
import http.client
from pathlib import Path
import runpy
import sys
from unittest.mock import patch
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
with ExitStack() as stack:
    guards=[]
    for target in ('socket.socket','socket.create_connection','socket.getaddrinfo','urllib.request.urlopen','http.client.HTTPConnection.connect','http.client.HTTPSConnection.connect'):
        guard=stack.enter_context(patch(target,side_effect=AssertionError('network is forbidden in CLI tests')));guards.append(guard)
    try:runpy.run_module('access_intake',run_name='__main__')
    finally:
        for guard in guards:guard.assert_not_called()
