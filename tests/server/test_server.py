def test_health(client):
    response = client.get("/ack/health")
    assert response.status_code == 200
    assert response.data == b"OK"


def test_home(client):
    response = client.get("/")
    assert response.status_code == 403
