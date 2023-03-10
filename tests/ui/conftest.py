import pytest

import builder
import settings


@pytest.fixture(scope="session", autouse=True)
def handle_server():
    print("! Starting local test server at {}".format(settings.TEST_URL_BASE))
    server = builder.setup_httpd(settings.TEST_PORT, settings.WEBSITE_RENDERPATH)
    yield
    print("! Shutting down local test server")
    server.terminate()
    server.join()

