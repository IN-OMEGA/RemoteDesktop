"""Ephemeral password credentials for isolated test hosts only."""
import secrets
from host.password_auth import PasswordAuth

TEST_PASSWORD='isolated-test-password'


def protect_test_host(state):
    auth=state.password_auth=PasswordAuth()
    salt=secrets.token_bytes(16)
    auth.verifier=(salt,auth.derive(TEST_PASSWORD,salt))
    return auth.issue()
