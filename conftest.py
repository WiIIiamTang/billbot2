import pytest
import os
import custom_cogs.functions as custompics

if os.getenv("RUNTIME_ENV") == "docker":
    import flaskapp
else:
    import server


@pytest.fixture()
def app():
    if os.getenv("RUNTIME_ENV") == "docker":
        app = flaskapp.app
    else:
        app = server.app

    app.config.update(
        {
            "TESTING": True,
        }
    )
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def custom_pics():
    return custompics
