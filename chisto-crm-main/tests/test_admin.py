"""Админка: вход, права ролей, справочники, пользователи."""

from conftest import ADMIN, ENG, EXEC_DDHIB, canonical_event, login, pair, post_event, read_headers


def test_login_and_me(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": ADMIN[0], "password": "wrong"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "nobody", "password": "x"}).status_code == 401
    login(client)
    me = client.get("/api/v1/auth/me").json()
    assert me["username"] == ADMIN[0] and me["roles"] == ["admin"] and "users.manage" in me["permissions"]
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/auth/me").status_code == 401


def test_engineer_crud_and_unique_phone(client):
    login(client)
    created = client.post("/api/v1/engineers", json={"full_name": "Новиков Олег", "phone": "89991112233"})
    assert created.status_code == 201 and created.json()["phone"] == "+79991112233"
    assert created.json()["engineer_id"] == "ENG-00005"
    duplicate = client.post("/api/v1/engineers", json={"full_name": "Двойник", "phone": "+79991112233"})
    assert duplicate.status_code == 409
    assert client.post("/api/v1/engineers", json={"full_name": "Без телефона", "phone": "abc"}).status_code == 422
    assignment = client.post("/api/v1/assignments", json={"engineer_id": "ENG-00005", "territory_id": "TERR-002"})
    assert assignment.status_code == 201
    engineer = client.get("/api/v1/engineers/ENG-00005").json()
    assert engineer["current_assignment"]["territory_name"] == "Правобережный округ"


def test_executor_types_link(client):
    login(client)
    vtype = client.post("/api/v1/violation-types", json={"name": "Разбитый контейнер"}).json()
    executor = client.post("/api/v1/executors", json={"name": "УК «Пример»", "violation_type_ids": [vtype["type_violation_id"]]})
    assert executor.status_code == 201
    executor_id = executor.json()["executor_id"]
    types = client.get(f"/api/v1/integration/executors/{executor_id}/violation-types", headers=read_headers()).json()
    assert [t["name"] for t in types["items"]] == ["Разбитый контейнер"]
    bad = client.patch(f"/api/v1/executors/{executor_id}", json={"violation_type_ids": ["VIOLATION-9999"]})
    assert bad.status_code == 422


def test_custom_role_limits_access(client):
    login(client)
    role = client.post("/api/v1/roles", json={"code": "viewer", "name": "Наблюдатель", "permissions": ["cases.read"]})
    assert role.status_code == 201
    assert client.post("/api/v1/roles", json={"code": "bad", "name": "Плохая", "permissions": ["root"]}).status_code == 422
    user = client.post("/api/v1/users", json={"username": "viewer1", "password": "viewer-password-1", "roles": ["viewer"]})
    assert user.status_code == 201
    client.post("/api/v1/auth/logout")
    login(client, "viewer1", "viewer-password-1")
    assert client.get("/api/v1/cases").status_code == 200
    assert client.get("/api/v1/engineers").status_code == 403
    assert client.get("/api/v1/users").status_code == 403


def test_password_change_ends_sessions(client):
    login(client)
    user_id = client.post("/api/v1/users", json={"username": "disp", "password": "dispatcher-pass-1",
                                                  "roles": ["dispatcher"]}).json()["id"]
    other = client.__class__(client.app)
    login(other, "disp", "dispatcher-pass-1")
    assert other.get("/api/v1/auth/me").status_code == 200
    client.patch(f"/api/v1/users/{user_id}", json={"password": "new-dispatcher-pass"})
    assert other.get("/api/v1/auth/me").status_code == 401


def test_admin_cannot_lock_self_out(client):
    login(client)
    me = client.get("/api/v1/auth/me").json()
    assert client.patch(f"/api/v1/users/{me['id']}", json={"is_active": False}).status_code == 409
    assert client.patch(f"/api/v1/users/{me['id']}", json={"roles": ["dispatcher"]}).status_code == 409
    assert client.patch("/api/v1/roles/admin", json={"permissions": []}).status_code == 409


def test_uk_master_sees_only_own_cases(client):
    pair(client)
    post_event(client, canonical_event())  # дело ДДХиБ
    login(client)
    client.post("/api/v1/users", json={"username": "uk1", "password": "uk-master-pass-1", "roles": ["uk_master"],
                                       "executor_id": "EXEC-0002"})
    client.post("/api/v1/users", json={"username": "uk2", "password": "uk-master-pass-2", "roles": ["uk_master"],
                                       "executor_id": EXEC_DDHIB})
    case_id = client.get("/api/v1/cases").json()["items"][0]["id"]
    client.post("/api/v1/auth/logout")
    login(client, "uk1", "uk-master-pass-1")
    assert client.get("/api/v1/cases").json()["total"] == 0
    assert client.get(f"/api/v1/cases/{case_id}").status_code == 404
    client.post("/api/v1/auth/logout")
    login(client, "uk2", "uk-master-pass-2")
    assert client.get("/api/v1/cases").json()["total"] == 1


def test_audit_records_actions(client):
    login(client)
    client.patch(f"/api/v1/engineers/{ENG}", json={"email": "Ivanov@Example.ru"})
    entries = client.get("/api/v1/audit").json()
    assert any(e["action"] == "engineer.updated" and e["entity_id"] == ENG for e in entries)
    assert client.get(f"/api/v1/engineers/{ENG}").json()["email"] == "ivanov@example.ru"


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_engineer_created_with_max_user_id(client):
    """MAX user ID задаётся при создании — бот (через DG) узнаёт инженера сразу, без регистрации по телефону."""
    login(client)
    created = client.post("/api/v1/engineers", json={"full_name": "Петров Пётр", "phone": "89991112244", "max_user_id": " 4567890 "})
    assert created.status_code == 201, created.text
    eng_id = created.json()["engineer_id"]
    assert created.json()["max_user_id"] == "4567890"
    identity = client.get("/api/v1/integration/assignments/bot-users/4567890", headers=read_headers())
    assert identity.status_code == 200 and identity.json()["engineer_id"] == eng_id
    # тот же MAX другому инженеру — 409 с именем владельца
    twin = client.post("/api/v1/engineers", json={"full_name": "Двойник", "phone": "89991112255", "max_user_id": "4567890"})
    assert twin.status_code == 409 and "Петров Пётр" in twin.json()["detail"]
    assert client.post("/api/v1/engineers", json={"full_name": "С пробелом", "phone": "89991112266", "max_user_id": "45 67"}).status_code == 422
    # пустая строка = не привязан
    blank = client.post("/api/v1/engineers", json={"full_name": "Без MAX", "phone": "89991112277", "max_user_id": ""})
    assert blank.status_code == 201 and blank.json()["max_user_id"] is None


def test_engineer_max_user_id_edit_and_pending_registration(client):
    """Правка MAX в карточке; запрос бота «на разборе» с этим ID закрывается привязкой."""
    from test_registration import register, request
    login(client)
    pending = register(client, request("max-new-user", "8 999 777-66-55")).json()
    assert pending["status"] == "pending_review"
    eng_id = client.post("/api/v1/engineers", json={"full_name": "Сидоров Семён", "phone": "89993334455"}).json()["engineer_id"]
    patched = client.patch(f"/api/v1/engineers/{eng_id}", json={"max_user_id": "max-new-user"})
    assert patched.status_code == 200 and patched.json()["max_user_id"] == "max-new-user"
    regs = client.get("/api/v1/registrations?status=pending_review").json()
    assert all(r["max_user_id"] != "max-new-user" for r in regs)
    resolved = [r for r in client.get("/api/v1/registrations").json() if r["registration_id"] == pending["registration_id"]][0]
    assert resolved["status"] == "registered" and resolved["engineer_id"] == eng_id
    # чужой MAX — 409, свой же повторно — 200, очистка — null
    client.post("/api/v1/engineers", json={"full_name": "Владелец MAX", "phone": "89993334466", "max_user_id": "max-taken"})
    assert client.patch(f"/api/v1/engineers/{eng_id}", json={"max_user_id": "max-taken"}).status_code == 409
    assert client.patch(f"/api/v1/engineers/{eng_id}", json={"max_user_id": "max-new-user"}).status_code == 200
    assert client.patch(f"/api/v1/engineers/{eng_id}", json={"max_user_id": None}).json()["max_user_id"] is None
    assert client.get("/api/v1/integration/assignments/bot-users/max-new-user", headers=read_headers()).status_code == 404
