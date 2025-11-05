"""Pytest configuration for tests with proxy SSL certificate issues."""

import ssl

import httpx

# Monkey-patch httpx to disable SSL verification globally for tests
# This is needed when using HTTPS_PROXY with self-signed certificates
original_init = httpx.AsyncClient.__init__


def patched_init(self, *args, **kwargs):
    # Force verify=False for all httpx AsyncClient instances
    kwargs["verify"] = False
    original_init(self, *args, **kwargs)


httpx.AsyncClient.__init__ = patched_init
