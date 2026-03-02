"""V2 expansion: all modules

Revision ID: v2_001
Revises: (initial)
Create Date: 2026-02-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "v2_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Tenant: add feature flags + agency columns ──
    op.add_column("tenants", sa.Column("feature_flags_json", JSONB, server_default="{}", nullable=False))
    op.add_column("tenants", sa.Column("is_agency", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("tenants", sa.Column("allow_shared_accounts", sa.Boolean(), server_default="false", nullable=False))

    # ── IntegrationGoogleAds: add MCC columns ──
    op.add_column("integrations_google_ads", sa.Column("manager_customer_id", sa.String(20), nullable=True))
    op.add_column("integrations_google_ads", sa.Column("is_manager", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("integrations_google_ads", sa.Column("accessible_accounts_synced_at", sa.DateTime(timezone=True), nullable=True))

    # ── BusinessProfile: add profit model columns ──
    op.add_column("business_profiles", sa.Column("avg_job_value", sa.Numeric(12, 2), server_default="0", nullable=False))
    op.add_column("business_profiles", sa.Column("gross_margin_pct", sa.Numeric(5, 2), server_default="0.50", nullable=False))
    op.add_column("business_profiles", sa.Column("close_rate_estimate", sa.Numeric(5, 2), server_default="0.25", nullable=False))
    op.add_column("business_profiles", sa.Column("refund_rate_estimate", sa.Numeric(5, 2), server_default="0.05", nullable=False))
    op.add_column("business_profiles", sa.Column("desired_profit_buffer_pct", sa.Numeric(5, 2), server_default="0.20", nullable=False))

    # ── MODULE 1: MCC / Agency ──
    op.create_table(
        "google_ads_accessible_accounts",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manager_customer_id", sa.String(20), nullable=False),
        sa.Column("customer_id", sa.String(20), nullable=False),
        sa.Column("descriptive_name", sa.String(255), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.Column("timezone", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_accessible_accounts_tenant", "google_ads_accessible_accounts", ["tenant_id"])
    op.create_index("ix_accessible_accounts_customer", "google_ads_accessible_accounts", ["customer_id"])

    op.create_table(
        "tenant_google_ads_bindings",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("google_customer_id", sa.String(20), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("label", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_bindings_tenant", "tenant_google_ads_bindings", ["tenant_id"])
    op.create_unique_constraint("uq_binding_customer", "tenant_google_ads_bindings", ["google_customer_id"])

    # ── MODULE 2: Conversion Truth Layer ──
    op.create_table(
        "integrations_ga4",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_id", sa.String(50), nullable=False),
        sa.Column("refresh_token_encrypted", sa.String(1024), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config_json", JSONB, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ga4_tenant", "integrations_ga4", ["tenant_id"])

    op.create_table(
        "tracking_health_reports",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),  # site_scan, ga4, gtm
        sa.Column("report_json", JSONB, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_tracking_health_tenant", "tracking_health_reports", ["tenant_id"])

    op.create_table(
        "offline_conversions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("google_customer_id", sa.String(20), nullable=False),
        sa.Column("gclid", sa.String(255), nullable=False),
        sa.Column("conversion_name", sa.String(255), nullable=False),
        sa.Column("conversion_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(10), server_default="USD"),
        sa.Column("status", sa.String(20), server_default="pending"),  # pending, uploaded, failed
        sa.Column("upload_id", UUID(as_uuid=False), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_offline_conv_tenant", "offline_conversions", ["tenant_id"])
    op.create_unique_constraint("uq_offline_conv_dedup", "offline_conversions", ["gclid", "conversion_name", "conversion_time"])

    op.create_table(
        "offline_conversion_uploads",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_url", sa.String(1024), nullable=True),
        sa.Column("mapped_fields_json", JSONB, server_default="{}", nullable=False),
        sa.Column("row_count", sa.Integer(), server_default="0"),
        sa.Column("success_count", sa.Integer(), server_default="0"),
        sa.Column("error_count", sa.Integer(), server_default="0"),
        sa.Column("results_json", JSONB, server_default="{}", nullable=False),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_offline_uploads_tenant", "offline_conversion_uploads", ["tenant_id"])

    # ── MODULE 3: Advanced Change Management ──
    op.create_table(
        "change_sets",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), server_default="draft"),  # draft, scheduled, applying, applied, rolled_back, failed
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_change_sets_tenant", "change_sets", ["tenant_id"])
    op.create_index("ix_change_sets_scheduled", "change_sets", ["scheduled_for"], postgresql_where=sa.text("status = 'scheduled'"))

    op.create_table(
        "change_set_items",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("change_set_id", UUID(as_uuid=False), sa.ForeignKey("change_sets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("change_log_id", UUID(as_uuid=False), sa.ForeignKey("change_logs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("apply_order", sa.Integer(), nullable=False),
    )
    op.create_index("ix_change_set_items_set", "change_set_items", ["change_set_id"])

    op.create_table(
        "freeze_windows",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_freeze_windows_tenant", "freeze_windows", ["tenant_id"])

    op.create_table(
        "rollback_policies",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rules_json", JSONB, server_default="[]", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_rollback_policies_tenant", "rollback_policies", ["tenant_id"])

    # ── MODULE 4: Connector Framework ──
    op.create_table(
        "connectors",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),  # crm, slack_webhook, email, meta_ads, tiktok_ads, youtube_ads, generic_webhook
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), server_default="disconnected"),  # disconnected, connected, error
        sa.Column("config_json", JSONB, server_default="{}", nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_connectors_tenant", "connectors", ["tenant_id"])

    op.create_table(
        "connector_events",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("connector_id", UUID(as_uuid=False), sa.ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),  # info, warning, error
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("payload_json", JSONB, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_connector_events_connector", "connector_events", ["connector_id"])

    # ── MODULE 5: Policy Compliance ──
    op.create_table(
        "policy_rules",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("category", sa.String(50), nullable=False),  # prohibited, misleading, trademark, restricted
        sa.Column("pattern", sa.String(500), nullable=False),
        sa.Column("severity", sa.String(20), server_default="warning"),  # info, warning, error
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_global", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "tenant_policy_overrides",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", UUID(as_uuid=False), sa.ForeignKey("policy_rules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_policy_overrides_tenant", "tenant_policy_overrides", ["tenant_id"])

    op.create_table(
        "policy_scan_results",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),  # ad, headline, description, extension
        sa.Column("entity_ref", sa.String(255), nullable=False),
        sa.Column("warnings_json", JSONB, server_default="[]", nullable=False),
        sa.Column("passed", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_policy_scans_tenant", "policy_scan_results", ["tenant_id"])

    # ── MODULE 6: Prompt-Injection Defense ──
    op.create_table(
        "extracted_snippets",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_url", sa.String(1024), nullable=False),
        sa.Column("snippet_text", sa.Text(), nullable=False),
        sa.Column("sanitized_text", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("category", sa.String(50), nullable=True),  # heading, paragraph, meta, structured_data
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_snippets_tenant", "extracted_snippets", ["tenant_id"])
    op.create_index("ix_snippets_hash", "extracted_snippets", ["content_hash"])

    # ── MODULE 7: Evaluation Framework ──
    op.create_table(
        "recommendation_outcomes",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("recommendation_id", UUID(as_uuid=False), sa.ForeignKey("recommendations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),  # 7, 14, 30
        sa.Column("actual_metrics_json", JSONB, server_default="{}", nullable=False),
        sa.Column("delta_json", JSONB, server_default="{}", nullable=False),
        sa.Column("labeled_outcome", sa.String(20), nullable=True),  # win, neutral, loss
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_rec_outcomes_rec", "recommendation_outcomes", ["recommendation_id"])

    op.create_table(
        "playbook_stats",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("industry", sa.String(100), nullable=False),
        sa.Column("metric_key", sa.String(100), nullable=False),
        sa.Column("stat_json", JSONB, server_default="{}", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_playbook_stat", "playbook_stats", ["industry", "metric_key"])

    # ── MODULE 8: Competitor Intel V2 ──
    op.create_table(
        "competitor_creatives",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("competitor_domain", sa.String(255), nullable=False),
        sa.Column("creative_json", JSONB, server_default="{}", nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_comp_creatives_tenant", "competitor_creatives", ["tenant_id"])

    op.create_table(
        "competitor_alerts",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),  # new_offer, headline_change, new_competitor, outranking_shift
        sa.Column("severity", sa.String(20), server_default="info"),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("metadata_json", JSONB, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_comp_alerts_tenant", "competitor_alerts", ["tenant_id"])

    # ── MODULE 9: Billing & Metering ──
    op.create_table(
        "billing_customers",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("stripe_customer_id", sa.String(255), nullable=False),
        sa.Column("stripe_subscription_id", sa.String(255), nullable=True),
        sa.Column("plan", sa.String(50), server_default="starter"),
        sa.Column("status", sa.String(20), server_default="active"),  # active, past_due, canceled, trialing
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "usage_counters",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("counters_json", JSONB, server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_usage_tenant_period", "usage_counters", ["tenant_id", "period_start"])

    op.create_table(
        "credit_ledger",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),  # seopix, serp, prompt
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_credit_ledger_tenant", "credit_ledger", ["tenant_id"])

    # ── MODULE 10: Alerting & Delivery ──
    op.create_table(
        "notification_channels",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),  # slack, email, webhook
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("config_json", JSONB, server_default="{}", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notif_channels_tenant", "notification_channels", ["tenant_id"])

    op.create_table(
        "notification_rules",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("channel_id", UUID(as_uuid=False), sa.ForeignKey("notification_channels.id", ondelete="CASCADE"), nullable=True),
        sa.Column("min_severity", sa.String(20), server_default="warning"),
        sa.Column("quiet_start_hour", sa.Integer(), nullable=True),
        sa.Column("quiet_end_hour", sa.Integer(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notif_rules_tenant", "notification_rules", ["tenant_id"])

    op.create_table(
        "notifications_sent",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=False), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("alert_id", UUID(as_uuid=False), nullable=True),
        sa.Column("channel_id", UUID(as_uuid=False), sa.ForeignKey("notification_channels.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload_json", JSONB, server_default="{}", nullable=False),
        sa.Column("status", sa.String(20), server_default="sent"),  # sent, failed, retrying
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notif_sent_tenant", "notifications_sent", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("notifications_sent")
    op.drop_table("notification_rules")
    op.drop_table("notification_channels")
    op.drop_table("credit_ledger")
    op.drop_table("usage_counters")
    op.drop_table("billing_customers")
    op.drop_table("competitor_alerts")
    op.drop_table("competitor_creatives")
    op.drop_table("playbook_stats")
    op.drop_table("recommendation_outcomes")
    op.drop_table("extracted_snippets")
    op.drop_table("policy_scan_results")
    op.drop_table("tenant_policy_overrides")
    op.drop_table("policy_rules")
    op.drop_table("connector_events")
    op.drop_table("connectors")
    op.drop_table("rollback_policies")
    op.drop_table("freeze_windows")
    op.drop_table("change_set_items")
    op.drop_table("change_sets")
    op.drop_table("offline_conversion_uploads")
    op.drop_table("offline_conversions")
    op.drop_table("tracking_health_reports")
    op.drop_table("integrations_ga4")
    op.drop_table("tenant_google_ads_bindings")
    op.drop_table("google_ads_accessible_accounts")
    op.drop_column("business_profiles", "desired_profit_buffer_pct")
    op.drop_column("business_profiles", "refund_rate_estimate")
    op.drop_column("business_profiles", "close_rate_estimate")
    op.drop_column("business_profiles", "gross_margin_pct")
    op.drop_column("business_profiles", "avg_job_value")
    op.drop_column("integrations_google_ads", "accessible_accounts_synced_at")
    op.drop_column("integrations_google_ads", "is_manager")
    op.drop_column("integrations_google_ads", "manager_customer_id")
    op.drop_column("tenants", "allow_shared_accounts")
    op.drop_column("tenants", "is_agency")
    op.drop_column("tenants", "feature_flags_json")
