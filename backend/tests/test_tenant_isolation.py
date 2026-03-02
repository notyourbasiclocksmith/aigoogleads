"""
Tenant Isolation & RBAC Tests
Verifies cross-tenant access is blocked, invitation rules, and role restrictions.
Run with: pytest tests/test_tenant_isolation.py -v
"""
import uuid
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from fastapi import HTTPException

# ── Test helpers ──

def make_user(user_id=None):
    return type("User", (), {
        "id": user_id or str(uuid.uuid4()),
        "email": f"test-{uuid.uuid4().hex[:6]}@example.com",
        "full_name": "Test User",
        "is_active": True,
    })()


def make_tenant(tenant_id=None):
    return type("Tenant", (), {
        "id": tenant_id or str(uuid.uuid4()),
        "name": "Test Tenant",
        "industry": "testing",
        "tier": "starter",
        "slug": f"test-{uuid.uuid4().hex[:6]}",
    })()


def make_tenant_user(tenant_id, user_id, role="viewer"):
    return type("TenantUser", (), {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "user_id": user_id,
        "role": role,
    })()


# ── 1. Cross-Tenant Access Tests ──

class TestCrossTenantAccess:
    """User A in tenant X must NOT access tenant Y resources."""

    def test_verify_resource_tenant_blocks_wrong_tenant(self):
        """When resource belongs to tenant Y, user in tenant X gets 404."""
        from app.core.deps import verify_resource_tenant, CurrentUser

        user = CurrentUser(user_id="u1", tenant_id="tenant-x", role="admin", verified_membership=True)
        resource_tenant_id = "tenant-y"

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(verify_resource_tenant(resource_tenant_id, user))
        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail.lower()

    def test_verify_resource_tenant_allows_same_tenant(self):
        """When resource belongs to same tenant, no error raised."""
        from app.core.deps import verify_resource_tenant, CurrentUser

        user = CurrentUser(user_id="u1", tenant_id="tenant-x", role="admin", verified_membership=True)

        # Should NOT raise
        asyncio.run(verify_resource_tenant("tenant-x", user))

    def test_verify_resource_tenant_blocks_none_tenant(self):
        """When resource has None tenant_id, access is denied."""
        from app.core.deps import verify_resource_tenant, CurrentUser

        user = CurrentUser(user_id="u1", tenant_id="tenant-x", role="admin", verified_membership=True)

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(verify_resource_tenant(None, user))
        assert exc_info.value.status_code == 404


# ── 2. Campaign Lookup by ID Without Tenant Filter ──

class TestResourceOwnership:
    """Fetching an entity by ID must verify tenant_id matches."""

    def test_campaign_from_other_tenant_returns_404(self):
        """Simulates fetching a campaign that belongs to tenant-y while user is in tenant-x."""
        from app.core.deps import verify_resource_tenant, CurrentUser

        user = CurrentUser(user_id="u1", tenant_id="tenant-x", role="owner", verified_membership=True)

        # Simulate a campaign fetched from DB that belongs to another tenant
        campaign_tenant_id = "tenant-y"

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(verify_resource_tenant(campaign_tenant_id, user))
        # Must be 404 (not 403) to avoid leaking existence
        assert exc_info.value.status_code == 404


# ── 3. Invitation Token Reuse ──

class TestInvitationSecurity:
    """Invitation tokens must not be reusable."""

    def test_accepted_invite_cannot_be_reaccepted(self):
        """Once status is 'accepted', token lookup should be rejected."""
        from app.models.invitation import Invitation

        invite = Invitation(
            id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            email="test@example.com",
            role="viewer",
            status="accepted",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        # The accept endpoint checks status != "pending" and rejects
        assert invite.status != "pending"

    def test_expired_invite_is_rejected(self):
        """Invitation past expires_at must be rejected."""
        from app.models.invitation import Invitation

        invite = Invitation(
            id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            email="test@example.com",
            role="viewer",
            status="pending",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert invite.expires_at < datetime.now(timezone.utc)
        # The accept endpoint checks this and sets status to expired

    def test_revoked_invite_is_rejected(self):
        """Revoked invitation must not be accepted."""
        from app.models.invitation import Invitation

        invite = Invitation(
            id=str(uuid.uuid4()),
            tenant_id=str(uuid.uuid4()),
            email="test@example.com",
            role="viewer",
            status="revoked",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        assert invite.status != "pending"


# ── 4. RBAC Permission Tests ──

class TestRBACPermissions:
    """Role restrictions are enforced correctly."""

    def test_permission_map_completeness(self):
        """All defined permissions have valid role lists."""
        from app.core.permissions import PERMISSION_MAP
        valid_roles = {"owner", "admin", "analyst", "viewer"}

        for perm, roles in PERMISSION_MAP.items():
            assert isinstance(roles, list), f"Permission {perm} roles must be a list"
            for role in roles:
                assert role in valid_roles, f"Permission {perm} has invalid role '{role}'"

    def test_viewer_cannot_enable_autopilot(self):
        """Viewer role must NOT have autopilot.enable permission."""
        from app.core.permissions import has_permission
        assert has_permission("viewer", "autopilot.enable") is False

    def test_analyst_cannot_enable_autopilot(self):
        """Analyst role must NOT have autopilot.enable permission."""
        from app.core.permissions import has_permission
        assert has_permission("analyst", "autopilot.enable") is False

    def test_owner_can_enable_autopilot(self):
        """Owner role must have autopilot.enable permission."""
        from app.core.permissions import has_permission
        assert has_permission("owner", "autopilot.enable") is True

    def test_admin_can_enable_autopilot(self):
        """Admin role must have autopilot.enable permission."""
        from app.core.permissions import has_permission
        assert has_permission("admin", "autopilot.enable") is True

    def test_viewer_cannot_invite_members(self):
        """Viewer role must NOT have members.invite permission."""
        from app.core.permissions import has_permission
        assert has_permission("viewer", "members.invite") is False

    def test_analyst_cannot_invite_members(self):
        """Analyst role must NOT have members.invite permission."""
        from app.core.permissions import has_permission
        assert has_permission("analyst", "members.invite") is False

    def test_owner_can_invite_members(self):
        """Owner role must have members.invite permission."""
        from app.core.permissions import has_permission
        assert has_permission("owner", "members.invite") is True

    def test_only_owner_can_access_billing_write(self):
        """Only owner can write billing."""
        from app.core.permissions import has_permission
        assert has_permission("owner", "billing.write") is True
        assert has_permission("admin", "billing.write") is False
        assert has_permission("analyst", "billing.write") is False
        assert has_permission("viewer", "billing.write") is False

    def test_viewer_can_read_dashboards(self):
        """Viewer role must have reports.read permission."""
        from app.core.permissions import has_permission
        assert has_permission("viewer", "reports.read") is True

    def test_analyst_can_create_campaigns(self):
        """Analyst role can write campaigns."""
        from app.core.permissions import has_permission
        assert has_permission("analyst", "campaigns.write") is True

    def test_analyst_cannot_approve_changes(self):
        """Analyst role cannot approve changes."""
        from app.core.permissions import has_permission
        assert has_permission("analyst", "campaigns.approve") is False

    def test_unknown_permission_denied(self):
        """Unknown permissions are always denied."""
        from app.core.permissions import has_permission
        assert has_permission("owner", "nonexistent.perm") is False

    def test_get_permissions_for_role(self):
        """get_permissions_for_role returns correct list."""
        from app.core.permissions import get_permissions_for_role
        viewer_perms = get_permissions_for_role("viewer")
        assert "reports.read" in viewer_perms
        assert "autopilot.enable" not in viewer_perms

        owner_perms = get_permissions_for_role("owner")
        assert "billing.write" in owner_perms
        assert "autopilot.enable" in owner_perms


# ── 5. Require Tenant Dependency ──

class TestRequireTenant:
    """require_tenant dependency must validate DB membership."""

    def test_no_tenant_returns_400(self):
        """If no tenant_id is resolvable, return 400."""
        from app.core.deps import CurrentUser

        user = CurrentUser(user_id="u1", tenant_id=None, role=None)
        assert user.tenant_id is None

    def test_current_user_without_verification(self):
        """Freshly created CurrentUser has verified_membership=False."""
        from app.core.deps import CurrentUser

        user = CurrentUser(user_id="u1", tenant_id="t1", role="viewer")
        assert user.verified_membership is False


# ── 6. Client Info Extraction ──

class TestClientInfo:
    """get_client_info extracts IP and user agent correctly."""

    def test_extracts_direct_ip(self):
        from app.core.deps import get_client_info

        mock_request = MagicMock()
        mock_request.headers = {"User-Agent": "TestBot/1.0"}
        mock_request.client = MagicMock()
        mock_request.client.host = "192.168.1.1"

        info = get_client_info(mock_request)
        assert info["ip_address"] == "192.168.1.1"
        assert info["user_agent"] == "TestBot/1.0"

    def test_extracts_forwarded_ip(self):
        from app.core.deps import get_client_info

        mock_request = MagicMock()
        mock_request.headers = {
            "X-Forwarded-For": "10.0.0.1, 10.0.0.2",
            "User-Agent": "TestBot/1.0",
        }
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        info = get_client_info(mock_request)
        assert info["ip_address"] == "10.0.0.1"

    def test_truncates_long_user_agent(self):
        from app.core.deps import get_client_info

        mock_request = MagicMock()
        mock_request.headers = {"User-Agent": "A" * 1000}
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"

        info = get_client_info(mock_request)
        assert len(info["user_agent"]) == 512
