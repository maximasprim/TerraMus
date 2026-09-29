import pytest

pytestmark = pytest.mark.asyncio


async def _setup_animal(client, org_name: str, email: str):
    reg = await client.post("/api/v1/auth/register", json={
        "organization_name": org_name, "full_name": "Owner",
        "email": email, "password": "supersecret123",
    })
    headers = {"Authorization": f"Bearer {reg.json()['access_token']}"}

    farm = await client.post("/api/v1/farms", json={"name": "Main Farm"}, headers=headers)
    farm_id = farm.json()["id"]
    branch = await client.post(f"/api/v1/farms/{farm_id}/branches", json={"name": "Branch A"}, headers=headers)
    branch_id = branch.json()["id"]
    loc = await client.post(
        f"/api/v1/farms/{farm_id}/branches/{branch_id}/locations",
        json={"name": "Paddock 1", "location_type": "paddock"}, headers=headers,
    )
    loc_id = loc.json()["id"]

    animal = await client.post("/api/v1/livestock", headers=headers, json={
        "farm_id": farm_id, "location_id": loc_id, "animal_number": "COW-NOTIF",
        "species": "cattle", "sex": "female", "acquisition_date": "2024-01-01",
        "acquisition_method": "purchased", "acquisition_cost": "40000",
    })
    return headers, animal.json()["id"]


async def test_order_created_notifies_orders_manage_holder(client):
    headers, animal_id = await _setup_animal(client, "Notif Farm A", "n1@example.com")
    await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})
    customer = await client.post("/api/v1/customers", headers=headers, json={"name": "Alice"})
    await client.post("/api/v1/orders", headers=headers, json={
        "customer_id": customer.json()["id"], "items": [{"animal_id": animal_id, "price": "50000"}],
    })

    notifications = (await client.get("/api/v1/notifications", headers=headers)).json()
    orders_notifs = [n for n in notifications if n["category"] == "orders"]
    assert len(orders_notifs) == 1
    assert "New order" in orders_notifs[0]["title"]
    assert orders_notifs[0]["is_read"] is False


async def test_vaccination_due_notifies_health_permission_holders(client):
    headers, animal_id = await _setup_animal(client, "Notif Farm B", "n2@example.com")
    await client.post(f"/api/v1/livestock/{animal_id}/health", headers=headers, json={
        "record_type": "vaccination", "title": "FMD", "follow_up_date": "2030-01-01",
    })
    notifications = (await client.get("/api/v1/notifications", headers=headers)).json()
    health_notifs = [n for n in notifications if n["category"] == "health"]
    assert len(health_notifs) == 1


async def test_mark_read_and_mark_all_read(client):
    headers, animal_id = await _setup_animal(client, "Notif Farm C", "n3@example.com")
    await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})
    customer = await client.post("/api/v1/customers", headers=headers, json={"name": "Alice"})
    await client.post("/api/v1/orders", headers=headers, json={
        "customer_id": customer.json()["id"], "items": [{"animal_id": animal_id, "price": "50000"}],
    })

    notifications = (await client.get("/api/v1/notifications", headers=headers)).json()
    notif_id = notifications[0]["id"]

    read = await client.post(f"/api/v1/notifications/{notif_id}/read", headers=headers)
    assert read.json()["is_read"] is True

    unread = (await client.get("/api/v1/notifications?unread_only=true", headers=headers)).json()
    assert len(unread) == 0

    mark_all = await client.post("/api/v1/notifications/read-all", headers=headers)
    assert mark_all.json()["marked_read"] == 0  # already all read


async def test_disabled_category_preference_suppresses_notification(client):
    headers, animal_id = await _setup_animal(client, "Notif Farm D", "n4@example.com")
    await client.put("/api/v1/notifications/preferences", headers=headers, json={
        "category": "orders", "enabled": False,
    })

    await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})
    customer = await client.post("/api/v1/customers", headers=headers, json={"name": "Alice"})
    await client.post("/api/v1/orders", headers=headers, json={
        "customer_id": customer.json()["id"], "items": [{"animal_id": animal_id, "price": "50000"}],
    })

    notifications = (await client.get("/api/v1/notifications", headers=headers)).json()
    orders_notifs = [n for n in notifications if n["category"] == "orders"]
    assert len(orders_notifs) == 0


async def test_run_scheduled_checks_expires_reservation_and_notifies(client):
    headers, animal_id = await _setup_animal(client, "Notif Farm E", "n5@example.com")
    await client.post(f"/api/v1/livestock/{animal_id}/status", headers=headers, json={"status": "for_sale"})
    customer = await client.post("/api/v1/customers", headers=headers, json={"name": "Alice"})
    await client.post("/api/v1/reservations", headers=headers, json={
        "animal_id": animal_id, "customer_id": customer.json()["id"],
        "reservation_date": "2020-01-01", "expiry_date": "2020-01-08",  # already expired
    })

    result = await client.post("/api/v1/notifications/run-scheduled-checks", headers=headers)
    assert result.json()["reservations_expired"] == 1

    animal = (await client.get(f"/api/v1/livestock/{animal_id}", headers=headers)).json()
    assert animal["status"] == "for_sale"  # released back

    notifications = (await client.get("/api/v1/notifications", headers=headers)).json()
    assert any(n["title"] == "Reservation expired" for n in notifications)


async def test_notifications_tenant_isolation(client):
    headers_a, animal_id_a = await _setup_animal(client, "Notif Iso A", "n6a@example.com")
    headers_b, _ = await _setup_animal(client, "Notif Iso B", "n6b@example.com")

    await client.post(f"/api/v1/livestock/{animal_id_a}/status", headers=headers_a, json={"status": "for_sale"})
    customer = await client.post("/api/v1/customers", headers=headers_a, json={"name": "Alice"})
    await client.post("/api/v1/orders", headers=headers_a, json={
        "customer_id": customer.json()["id"], "items": [{"animal_id": animal_id_a, "price": "50000"}],
    })

    notifs_b = (await client.get("/api/v1/notifications", headers=headers_b)).json()
    assert len(notifs_b) == 0  # Org B never sees Org A's order notification
