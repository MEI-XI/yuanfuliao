from conftest import bootstrap


def test_first_install_creates_admin_and_closes_setup(client):
    assert client.get("/api/setup").json() == {"required": True}
    administrator = bootstrap(client)
    assert administrator["role"] == "superadmin"
    assert client.get("/api/me").json()["username"] == "admin"
    assert client.get("/api/setup").json() == {"required": False}
    response = client.post("/api/setup", json={"username": "intruder", "password": "other-password-123"})
    assert response.status_code == 409


def test_admin_controls_accounts_and_disabling_revokes_access(client):
    bootstrap(client)
    created = client.post("/api/users", json={"username": "worker", "password": "worker-password", "role": "user"})
    assert created.status_code == 201
    worker = created.json()
    assert "password_hash" not in worker
    admin_cookie = client.cookies.get("session")
    assert client.post("/api/login", json={"username": "worker", "password": "worker-password"}).status_code == 200
    worker_cookie = client.cookies.get("session")
    assert client.post("/api/users", json={"username": "evil", "password": "worker-password", "role": "admin"}).status_code == 403
    assert client.patch(f'/api/users/{worker["id"]}', json={"role": "admin"}).status_code == 403
    client.cookies.set("session", admin_cookie)
    assert client.patch(f'/api/users/{worker["id"]}', json={"active": False}).status_code == 200
    client.cookies.set("session", worker_cookie)
    assert client.get("/api/me").status_code == 401


def test_account_maintenance_cannot_remove_the_last_active_administrator(client):
    admin = bootstrap(client)
    assert client.patch(f'/api/users/{admin["id"]}', json={"role": "user"}).status_code == 409
    assert client.patch(f'/api/users/{admin["id"]}', json={"active": False}).status_code == 409
    assert client.get('/api/me').json()['role'] == 'superadmin'
