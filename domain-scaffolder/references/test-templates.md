# Test Templates for Backend Scaffolding

> These templates use `{backend_module}` as a placeholder for your project's import path.
> Replace with the actual import path defined in your mode file (e.g., `my_server.domains`).
> Adapt test framework syntax and fixtures to match your mode's `test_framework` setting.

## Service Test Template

```python
"""Tests for {slice} service layer."""
import pytest
from uuid import uuid4

from {backend_module}.{slice}.service import {Slice}Service
from {backend_module}.{slice}.schemas import {Schema}Create, {Schema}Update


class Test{Slice}Service:
    """Unit tests for {Slice}Service."""

    @pytest.fixture
    def service(self, db_session) -> {Slice}Service:
        """Create service instance with test session."""
        return {Slice}Service(db_session)

    # =========================================================================
    # CREATE TESTS
    # =========================================================================

    async def test_create_success(
        self,
        service: {Slice}Service,
        owner_id: str,
    ):
        """Test successful creation with valid data."""
        data = {Schema}Create(
            # Required fields from shared.md
        )
        result = await service.create_{item}(owner_id, data)

        assert result.id is not None
        assert result.created_at is not None
        # Assert all fields match input

    async def test_create_duplicate_raises_already_exists(
        self,
        service: {Slice}Service,
        existing_{item},
    ):
        """Test creating duplicate raises ALREADY_EXISTS error."""
        data = {Schema}Create(
            # Same unique field as existing
        )
        with pytest.raises(ValueError, match="{SLICE}_ALREADY_EXISTS"):
            await service.create_{item}(data)

    async def test_create_invalid_reference_raises_error(
        self,
        service: {Slice}Service,
    ):
        """Test creating with invalid foreign key raises error."""
        data = {Schema}Create(
            parent_id=uuid4(),  # Non-existent
        )
        with pytest.raises(ValueError, match="PARENT_NOT_FOUND"):
            await service.create_{item}(data)

    # =========================================================================
    # READ TESTS
    # =========================================================================

    async def test_get_by_id_success(
        self,
        service: {Slice}Service,
        existing_{item},
    ):
        """Test getting item by ID returns correct data."""
        result = await service.get_{item}(existing_{item}.id)

        assert result.id == existing_{item}.id
        # Assert all fields

    async def test_get_by_id_not_found(
        self,
        service: {Slice}Service,
    ):
        """Test getting non-existent ID raises NOT_FOUND."""
        with pytest.raises(ValueError, match="{SLICE}_NOT_FOUND"):
            await service.get_{item}(uuid4())

    async def test_list_returns_filtered_items(
        self,
        service: {Slice}Service,
        seed_items,  # Multiple items with different attributes
    ):
        """Test listing with filters returns correct subset."""
        result = await service.list_{items}(
            owner_id=seed_items[0].owner_id,
            # Other filters
        )

        assert len(result) > 0
        assert all(item.owner_id == seed_items[0].owner_id for item in result)

    async def test_list_empty_returns_empty_list(
        self,
        service: {Slice}Service,
    ):
        """Test listing with no matches returns empty list."""
        result = await service.list_{items}(
            owner_id=uuid4(),  # No items for this owner
        )

        assert result == []

    # =========================================================================
    # UPDATE TESTS
    # =========================================================================

    async def test_update_success(
        self,
        service: {Slice}Service,
        existing_{item},
    ):
        """Test successful update with valid data."""
        update_data = {Schema}Update(
            # Fields to update
        )
        result = await service.update_{item}(existing_{item}.id, update_data)

        assert result.id == existing_{item}.id
        # Assert updated fields changed
        # Assert non-updated fields unchanged

    async def test_update_not_found(
        self,
        service: {Slice}Service,
    ):
        """Test updating non-existent item raises NOT_FOUND."""
        with pytest.raises(ValueError, match="{SLICE}_NOT_FOUND"):
            await service.update_{item}(uuid4(), {Schema}Update())

    async def test_update_partial_only_changes_provided_fields(
        self,
        service: {Slice}Service,
        existing_{item},
    ):
        """Test partial update only modifies provided fields."""
        original_field = existing_{item}.some_field
        update_data = {Schema}Update(other_field="new_value")

        result = await service.update_{item}(existing_{item}.id, update_data)

        assert result.some_field == original_field  # Unchanged
        assert result.other_field == "new_value"    # Changed

    # =========================================================================
    # DELETE TESTS
    # =========================================================================

    async def test_delete_success(
        self,
        service: {Slice}Service,
        existing_{item},
    ):
        """Test successful deletion."""
        await service.delete_{item}(existing_{item}.id)

        # Verify deleted
        with pytest.raises(ValueError, match="{SLICE}_NOT_FOUND"):
            await service.get_{item}(existing_{item}.id)

    async def test_delete_not_found(
        self,
        service: {Slice}Service,
    ):
        """Test deleting non-existent item raises NOT_FOUND."""
        with pytest.raises(ValueError, match="{SLICE}_NOT_FOUND"):
            await service.delete_{item}(uuid4())

    async def test_delete_with_dependents_raises_error(
        self,
        service: {Slice}Service,
        {item}_with_children,
    ):
        """Test deleting item with dependents raises error."""
        with pytest.raises(ValueError, match="{SLICE}_HAS_DEPENDENTS"):
            await service.delete_{item}({item}_with_children.id)

    # =========================================================================
    # PERMISSION TESTS (if applicable)
    # =========================================================================

    async def test_access_other_owner_data_raises_no_access(
        self,
        service: {Slice}Service,
        other_owner_{item},
    ):
        """Test accessing another owner's data raises NO_ACCESS."""
        with pytest.raises(ValueError, match="{SLICE}_NO_ACCESS"):
            await service.get_{item}(
                other_owner_{item}.id,
                owner_id=uuid4(),  # Different owner
            )
```

## Route Test Template

```python
"""API route tests for {slice} domain."""
import pytest
from uuid import uuid4


class Test{Slice}Routes:
    """Integration tests for {slice} API endpoints."""

    # =========================================================================
    # LIST ENDPOINT
    # =========================================================================

    async def test_list_success(
        self,
        client,
        auth_headers: dict,
        seed_{items},
    ):
        """GET /v1/{slice} returns paginated list."""
        response = await client.get(
            "/v1/{slice}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data or isinstance(data, list)

    async def test_list_with_filters(
        self,
        client,
        auth_headers: dict,
        seed_{items},
    ):
        """GET /v1/{slice}?filter=value returns filtered list."""
        response = await client.get(
            "/v1/{slice}",
            params={"status": "active"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # Assert filter applied

    async def test_list_unauthorized(
        self,
        client,
    ):
        """GET /v1/{slice} without auth returns 401."""
        response = await client.get("/v1/{slice}")
        assert response.status_code == 401

    # =========================================================================
    # GET SINGLE ENDPOINT
    # =========================================================================

    async def test_get_success(
        self,
        client,
        auth_headers: dict,
        existing_{item},
    ):
        """GET /v1/{slice}/{id} returns item."""
        response = await client.get(
            f"/v1/{slice}/{existing_{item}.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(existing_{item}.id)

    async def test_get_not_found(
        self,
        client,
        auth_headers: dict,
    ):
        """GET /v1/{slice}/{id} with invalid ID returns 404."""
        response = await client.get(
            f"/v1/{slice}/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "{SLICE}_NOT_FOUND"

    # =========================================================================
    # CREATE ENDPOINT
    # =========================================================================

    async def test_create_success(
        self,
        client,
        auth_headers: dict,
    ):
        """POST /v1/{slice} creates and returns item."""
        response = await client.post(
            "/v1/{slice}",
            json={
                # Required fields from shared.md
            },
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data

    async def test_create_validation_error(
        self,
        client,
        auth_headers: dict,
    ):
        """POST /v1/{slice} with invalid data returns 422."""
        response = await client.post(
            "/v1/{slice}",
            json={},  # Missing required fields
            headers=auth_headers,
        )

        assert response.status_code == 422

    async def test_create_duplicate_returns_409(
        self,
        client,
        auth_headers: dict,
        existing_{item},
    ):
        """POST /v1/{slice} with duplicate unique field returns 409."""
        response = await client.post(
            "/v1/{slice}",
            json={
                "unique_field": existing_{item}.unique_field,
            },
            headers=auth_headers,
        )

        assert response.status_code == 409
        assert response.json()["detail"] == "{SLICE}_ALREADY_EXISTS"

    # =========================================================================
    # UPDATE ENDPOINT
    # =========================================================================

    async def test_update_success(
        self,
        client,
        auth_headers: dict,
        existing_{item},
    ):
        """PUT/PATCH /v1/{slice}/{id} updates and returns item."""
        response = await client.patch(
            f"/v1/{slice}/{existing_{item}.id}",
            json={"field": "new_value"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["field"] == "new_value"

    async def test_update_not_found(
        self,
        client,
        auth_headers: dict,
    ):
        """PUT/PATCH /v1/{slice}/{id} with invalid ID returns 404."""
        response = await client.patch(
            f"/v1/{slice}/{uuid4()}",
            json={"field": "value"},
            headers=auth_headers,
        )

        assert response.status_code == 404

    # =========================================================================
    # DELETE ENDPOINT
    # =========================================================================

    async def test_delete_success(
        self,
        client,
        auth_headers: dict,
        existing_{item},
    ):
        """DELETE /v1/{slice}/{id} returns 204."""
        response = await client.delete(
            f"/v1/{slice}/{existing_{item}.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

    async def test_delete_not_found(
        self,
        client,
        auth_headers: dict,
    ):
        """DELETE /v1/{slice}/{id} with invalid ID returns 404."""
        response = await client.delete(
            f"/v1/{slice}/{uuid4()}",
            headers=auth_headers,
        )

        assert response.status_code == 404
```

## Conftest Fixtures Template

```python
# tests/domains/{slice}/conftest.py
"""Fixtures for {slice} domain tests."""
import pytest
from uuid import uuid4

from {backend_module}.{slice}.models import {Model}


@pytest.fixture
def sample_{item}_data() -> dict:
    """Sample data for creating a {item}."""
    return {
        # Fields from shared.md
    }


@pytest.fixture
async def existing_{item}(
    db_session,
    owner_id: str,
) -> {Model}:
    """Create and return an existing {item} for tests."""
    {item} = {Model}(
        id=uuid4(),
        owner_id=owner_id,
        # Other fields
    )
    db_session.add({item})
    await db_session.commit()
    await db_session.refresh({item})
    return {item}


@pytest.fixture
async def seed_{items}(
    db_session,
    owner_id: str,
) -> list[{Model}]:
    """Create multiple {items} for list tests."""
    {items} = [
        {Model}(id=uuid4(), owner_id=owner_id, status="active"),
        {Model}(id=uuid4(), owner_id=owner_id, status="inactive"),
        {Model}(id=uuid4(), owner_id=owner_id, status="active"),
    ]
    db_session.add_all({items})
    await db_session.commit()
    return {items}
```

## Error Code HTTP Status Mapping

From shared.md, map error codes to HTTP status:

| Error Code Pattern | HTTP Status | When |
|--------------------|-------------|------|
| `*_NOT_FOUND` | 404 | Resource does not exist |
| `*_ALREADY_EXISTS` | 409 | Unique constraint violation |
| `*_NO_ACCESS` | 403 | Permission denied |
| `*_INVALID_*` | 400 | Validation error |
| `*_HAS_DEPENDENTS` | 400 | Cannot delete with children |

```python
ERROR_STATUS_MAP = {
    "{SLICE}_NOT_FOUND": 404,
    "{SLICE}_ALREADY_EXISTS": 409,
    "{SLICE}_NO_ACCESS": 403,
    "{SLICE}_INVALID_DATA": 400,
    "{SLICE}_HAS_DEPENDENTS": 400,
}
```
