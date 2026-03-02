"""
Centralized RBAC Permission Map
Maps permissions to allowed roles. Backend enforcement is the real security layer.
"""

# Role hierarchy: owner > admin > analyst > viewer
ROLE_HIERARCHY = {
    "owner": 4,
    "admin": 3,
    "analyst": 2,
    "viewer": 1,
}

# Permission → minimum roles allowed
PERMISSION_MAP = {
    # Tenant management
    "tenant.delete": ["owner"],
    "tenant.billing": ["owner"],
    "tenant.settings.write": ["owner", "admin"],
    "tenant.settings.read": ["owner", "admin", "analyst", "viewer"],

    # Member management
    "members.invite": ["owner", "admin"],
    "members.remove": ["owner", "admin"],
    "members.role_change": ["owner", "admin"],
    "members.list": ["owner", "admin", "analyst", "viewer"],

    # Google Ads integration
    "integration.connect": ["owner", "admin"],
    "integration.disconnect": ["owner", "admin"],
    "integration.read": ["owner", "admin", "analyst", "viewer"],

    # Campaigns
    "campaigns.write": ["owner", "admin", "analyst"],
    "campaigns.read": ["owner", "admin", "analyst", "viewer"],
    "campaigns.approve": ["owner", "admin"],

    # Autopilot
    "autopilot.enable": ["owner", "admin"],
    "autopilot.configure": ["owner", "admin"],

    # Change management
    "changes.apply": ["owner", "admin"],
    "changes.rollback": ["owner", "admin"],
    "changes.create": ["owner", "admin", "analyst"],
    "changes.read": ["owner", "admin", "analyst", "viewer"],
    "changes.freeze_window": ["owner", "admin"],

    # Creative / Prompts
    "creative.write": ["owner", "admin", "analyst"],
    "creative.read": ["owner", "admin", "analyst", "viewer"],

    # Reports
    "reports.read": ["owner", "admin", "analyst", "viewer"],
    "reports.export": ["owner", "admin", "analyst"],

    # Recommendations
    "recommendations.read": ["owner", "admin", "analyst", "viewer"],
    "recommendations.apply": ["owner", "admin"],
    "recommendations.create": ["owner", "admin", "analyst"],

    # Competitors / Intel
    "intel.read": ["owner", "admin", "analyst", "viewer"],
    "intel.write": ["owner", "admin"],

    # Connectors
    "connectors.write": ["owner", "admin"],
    "connectors.read": ["owner", "admin", "analyst", "viewer"],

    # Policy
    "policy.scan": ["owner", "admin", "analyst"],
    "policy.rules.write": ["owner", "admin"],
    "policy.read": ["owner", "admin", "analyst", "viewer"],

    # Billing
    "billing.read": ["owner", "admin"],
    "billing.write": ["owner"],

    # Notifications
    "notifications.write": ["owner", "admin"],
    "notifications.read": ["owner", "admin", "analyst", "viewer"],

    # Evaluation
    "evaluation.read": ["owner", "admin", "analyst", "viewer"],
    "evaluation.write": ["owner", "admin"],

    # Audit
    "audit.read": ["owner", "admin"],
}


def has_permission(role: str, permission: str) -> bool:
    """Check if a role has a specific permission."""
    allowed_roles = PERMISSION_MAP.get(permission)
    if allowed_roles is None:
        return False
    return role in allowed_roles


def get_permissions_for_role(role: str) -> list[str]:
    """Get all permissions for a given role."""
    return [perm for perm, roles in PERMISSION_MAP.items() if role in roles]
