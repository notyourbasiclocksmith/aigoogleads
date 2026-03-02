from app.models.tenant import Tenant
from app.models.user import User
from app.models.tenant_user import TenantUser
from app.models.integration_google_ads import IntegrationGoogleAds
from app.models.business_profile import BusinessProfile
from app.models.crawled_page import CrawledPage
from app.models.social_profile import SocialProfile
from app.models.ads_account_cache import AdsAccountCache
from app.models.campaign import Campaign
from app.models.ad_group import AdGroup
from app.models.ad import Ad
from app.models.keyword import Keyword
from app.models.negative import Negative
from app.models.asset import Asset
from app.models.conversion import Conversion
from app.models.performance_daily import PerformanceDaily
from app.models.auction_insight import AuctionInsight
from app.models.serp_scan import SerpScan
from app.models.competitor_profile import CompetitorProfile
from app.models.recommendation import Recommendation
from app.models.change_log import ChangeLog
from app.models.approval import Approval
from app.models.experiment import Experiment
from app.models.playbook import Playbook
from app.models.learning import Learning
from app.models.alert import Alert
from app.models.user_session import UserSession
from app.models.invitation import Invitation
from app.models.audit_event import AuditEvent
from app.models.tenant_settings import TenantSettings

__all__ = [
    "Tenant", "User", "TenantUser", "IntegrationGoogleAds",
    "BusinessProfile", "CrawledPage", "SocialProfile", "AdsAccountCache",
    "Campaign", "AdGroup", "Ad", "Keyword", "Negative", "Asset",
    "Conversion", "PerformanceDaily", "AuctionInsight", "SerpScan",
    "CompetitorProfile", "Recommendation", "ChangeLog", "Approval",
    "Experiment", "Playbook", "Learning", "Alert",
    "UserSession", "Invitation", "AuditEvent", "TenantSettings",
]

# V2 Models — imported so Alembic/ORM can discover them
from app.models.v2 import (  # noqa: E402, F401
    GoogleAdsAccessibleAccount, TenantGoogleAdsBinding,
    IntegrationGA4, TrackingHealthReport,
    OfflineConversion, OfflineConversionUpload,
    ChangeSet, ChangeSetItem, FreezeWindow, RollbackPolicy,
    Connector, ConnectorEvent,
    PolicyRule, TenantPolicyOverride, PolicyScanResult,
    ExtractedSnippet,
    RecommendationOutcome, PlaybookStat,
    CompetitorCreative, CompetitorAlert,
    BillingCustomer, UsageCounter, CreditLedgerEntry,
    NotificationChannel, NotificationRule, NotificationSent,
)
