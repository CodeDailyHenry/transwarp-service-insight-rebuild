import pytest
from sqlalchemy import URL

from sla_assistant.identity import Identity, IdentityError


def test_initial_admin_survives_restart_and_cannot_be_bootstrapped_twice(
    identity_url: str | URL,
) -> None:
    url = identity_url
    identity = Identity.open(url)
    issued = identity.bootstrap("maintainer")
    assert issued.user.role == "admin"
    assert identity.authenticate(issued.token) == issued.user
    identity.close()

    reopened = Identity.open(url)
    assert reopened.authenticate(issued.token).username == "maintainer"
    with pytest.raises(IdentityError, match="already initialized"):
        reopened.bootstrap("another-admin")
    assert issued.token not in repr(issued)
    reopened.close()
