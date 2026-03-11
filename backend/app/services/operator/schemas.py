"""
Pydantic schemas for the AI Campaign Operator data pipeline.
All Google Ads data is normalized into these schemas for analysis.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


# ── Enums ────────────────────────────────────────────────────────────────────

class ScanGoal(str, Enum):
    REDUCE_WASTE = "reduce_waste"
    INCREASE_CONVERSIONS = "increase_conversions"
    IMPROVE_CPA = "improve_cpa"
    SCALE_WINNERS = "scale_winners"
    FULL_REVIEW = "full_review"


class ScanStatus(str, Enum):
    QUEUED = "queued"
    COLLECTING_DATA = "collecting_data"
    ANALYZING = "analyzing"
    GENERATING_RECOMMENDATIONS = "generating_recommendations"
    BUILDING_PROJECTIONS = "building_projections"
    RUNNING_CREATIVE_AUDIT = "running_creative_audit"
    READY = "ready"
    FAILED = "failed"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RecType(str, Enum):
    PAUSE_KEYWORD = "PAUSE_KEYWORD"
    ADD_NEGATIVE_KEYWORD = "ADD_NEGATIVE_KEYWORD"
    LOWER_KEYWORD_BID = "LOWER_KEYWORD_BID"
    RAISE_KEYWORD_BID = "RAISE_KEYWORD_BID"
    CREATE_AD_GROUP = "CREATE_AD_GROUP"
    SPLIT_AD_GROUP = "SPLIT_AD_GROUP"
    CREATE_CAMPAIGN = "CREATE_CAMPAIGN"
    PAUSE_AD = "PAUSE_AD"
    CREATE_AD_VARIANTS = "CREATE_AD_VARIANTS"
    REWRITE_RSA = "REWRITE_RSA"
    ADD_ASSETS = "ADD_ASSETS"
    ADD_SITELINKS = "ADD_SITELINKS"
    ADD_CALLOUTS = "ADD_CALLOUTS"
    INCREASE_BUDGET = "INCREASE_BUDGET"
    DECREASE_BUDGET = "DECREASE_BUDGET"
    CHANGE_BIDDING_STRATEGY = "CHANGE_BIDDING_STRATEGY"
    ADD_LOCATION = "ADD_LOCATION"
    EXCLUDE_LOCATION = "EXCLUDE_LOCATION"
    ADJUST_DEVICE_MODIFIER = "ADJUST_DEVICE_MODIFIER"
    ADD_AD_SCHEDULE_RULE = "ADD_AD_SCHEDULE_RULE"
    CREATE_EXPERIMENT = "CREATE_EXPERIMENT"
    RESTRUCTURE_THEME_CLUSTER = "RESTRUCTURE_THEME_CLUSTER"
    ADD_BRAND_SPECIFIC_CAMPAIGN = "ADD_BRAND_SPECIFIC_CAMPAIGN"
    ADD_HIGH_INTENT_CAMPAIGN = "ADD_HIGH_INTENT_CAMPAIGN"
    POLICY_FIX = "POLICY_FIX"
    IMAGE_REFRESH = "IMAGE_REFRESH"
    CREATE_IMAGE_ASSET_PACK = "CREATE_IMAGE_ASSET_PACK"


class RecGroup(str, Enum):
    BUDGET_BIDDING = "budget_bidding"
    KEYWORDS_SEARCH_TERMS = "keywords_search_terms"
    NEGATIVE_KEYWORDS = "negative_keywords"
    CAMPAIGN_STRUCTURE = "campaign_structure"
    AD_GROUPS = "ad_groups"
    AD_COPY = "ad_copy"
    CREATIVE_ASSETS = "creative_assets"
    DEVICE_MODIFIERS = "device_modifiers"
    GEO_TARGETING = "geo_targeting"
    AD_SCHEDULE = "ad_schedule"
    AUDIENCE_SIGNALS = "audience_signals"
    EXTENSIONS_ASSETS = "extensions_assets"
    NEW_CAMPAIGNS = "new_campaigns"
    POLICY_COMPLIANCE = "policy_compliance"


# ── Collected Data Schemas ───────────────────────────────────────────────────

class CampaignData(BaseModel):
    campaign_id: str
    name: str
    status: str
    campaign_type: str = ""
    budget_amount_micros: int = 0
    budget_daily: float = 0.0
    bidding_strategy: str = ""
    target_cpa_micros: Optional[int] = None
    target_roas: Optional[float] = None
    geo_targets: List[str] = Field(default_factory=list)
    languages: List[str] = Field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None

    # Metrics for the analysis window
    impressions: int = 0
    clicks: int = 0
    cost_micros: int = 0
    conversions: float = 0.0
    conversion_value: float = 0.0
    ctr: float = 0.0
    avg_cpc: float = 0.0
    cost: float = 0.0
    conv_rate: float = 0.0
    cost_per_conversion: float = 0.0
    roas: float = 0.0
    search_impression_share: Optional[float] = None
    search_top_impression_share: Optional[float] = None
    search_abs_top_impression_share: Optional[float] = None
    search_lost_is_budget: Optional[float] = None
    search_lost_is_rank: Optional[float] = None


class AdGroupData(BaseModel):
    ad_group_id: str
    campaign_id: str
    name: str
    status: str
    cpc_bid_micros: Optional[int] = None

    impressions: int = 0
    clicks: int = 0
    cost_micros: int = 0
    cost: float = 0.0
    conversions: float = 0.0
    conversion_value: float = 0.0
    ctr: float = 0.0
    avg_cpc: float = 0.0
    conv_rate: float = 0.0
    cost_per_conversion: float = 0.0


class KeywordData(BaseModel):
    keyword_id: str
    ad_group_id: str
    campaign_id: str
    text: str
    match_type: str
    status: str
    quality_score: Optional[int] = None
    first_page_cpc_micros: Optional[int] = None

    impressions: int = 0
    clicks: int = 0
    cost_micros: int = 0
    cost: float = 0.0
    conversions: float = 0.0
    ctr: float = 0.0
    avg_cpc: float = 0.0
    conv_rate: float = 0.0
    cost_per_conversion: float = 0.0


class SearchTermData(BaseModel):
    search_term: str
    campaign_id: str
    ad_group_id: str
    keyword_text: Optional[str] = None

    impressions: int = 0
    clicks: int = 0
    cost_micros: int = 0
    cost: float = 0.0
    conversions: float = 0.0
    ctr: float = 0.0
    cost_per_conversion: float = 0.0


class AdData(BaseModel):
    ad_id: str
    ad_group_id: str
    campaign_id: str
    ad_type: str = ""
    headlines: List[str] = Field(default_factory=list)
    descriptions: List[str] = Field(default_factory=list)
    final_url: Optional[str] = None
    ad_strength: Optional[str] = None

    impressions: int = 0
    clicks: int = 0
    cost_micros: int = 0
    cost: float = 0.0
    conversions: float = 0.0
    ctr: float = 0.0
    conv_rate: float = 0.0
    cost_per_conversion: float = 0.0


class DeviceSegment(BaseModel):
    device: str  # MOBILE, DESKTOP, TABLET
    campaign_id: str
    impressions: int = 0
    clicks: int = 0
    cost: float = 0.0
    conversions: float = 0.0
    ctr: float = 0.0
    conv_rate: float = 0.0
    cost_per_conversion: float = 0.0


class DayOfWeekSegment(BaseModel):
    day_of_week: str
    campaign_id: str
    impressions: int = 0
    clicks: int = 0
    cost: float = 0.0
    conversions: float = 0.0
    cost_per_conversion: float = 0.0


class HourOfDaySegment(BaseModel):
    hour: int
    campaign_id: str
    impressions: int = 0
    clicks: int = 0
    cost: float = 0.0
    conversions: float = 0.0


class GeoSegment(BaseModel):
    location_name: str
    location_id: Optional[str] = None
    campaign_id: str
    impressions: int = 0
    clicks: int = 0
    cost: float = 0.0
    conversions: float = 0.0
    cost_per_conversion: float = 0.0


class NegativeKeywordData(BaseModel):
    keyword_text: str
    match_type: str
    level: str  # campaign, ad_group
    parent_id: str  # campaign_id or ad_group_id


# ── Full Account Snapshot ────────────────────────────────────────────────────

class AccountSnapshot(BaseModel):
    """Complete normalized account data for the analysis window."""
    customer_id: str
    date_range_start: str
    date_range_end: str
    currency_code: str = "USD"

    campaigns: List[CampaignData] = Field(default_factory=list)
    ad_groups: List[AdGroupData] = Field(default_factory=list)
    keywords: List[KeywordData] = Field(default_factory=list)
    search_terms: List[SearchTermData] = Field(default_factory=list)
    ads: List[AdData] = Field(default_factory=list)
    negatives: List[NegativeKeywordData] = Field(default_factory=list)

    device_segments: List[DeviceSegment] = Field(default_factory=list)
    day_of_week_segments: List[DayOfWeekSegment] = Field(default_factory=list)
    hour_of_day_segments: List[HourOfDaySegment] = Field(default_factory=list)
    geo_segments: List[GeoSegment] = Field(default_factory=list)

    # Totals
    total_spend: float = 0.0
    total_conversions: float = 0.0
    total_clicks: int = 0
    total_impressions: int = 0
    total_conversion_value: float = 0.0

    @property
    def avg_cpa(self) -> float:
        return self.total_spend / self.total_conversions if self.total_conversions > 0 else 0.0

    @property
    def avg_ctr(self) -> float:
        return self.total_clicks / self.total_impressions if self.total_impressions > 0 else 0.0

    @property
    def overall_roas(self) -> float:
        return self.total_conversion_value / self.total_spend if self.total_spend > 0 else 0.0


# ── Recommendation Output Schema ────────────────────────────────────────────

class ImpactProjection(BaseModel):
    spend_delta: float = 0.0  # positive = more spend, negative = savings
    click_delta: float = 0.0
    conversion_delta: float = 0.0
    cpa_delta: float = 0.0
    roas_delta: float = 0.0
    scenarios: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    # {conservative: {conversions: X, cpa: Y}, base: {...}, upside: {...}}
    assumptions: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    confidence: float = 0.5


class RecommendationOutput(BaseModel):
    recommendation_type: RecType
    group_name: RecGroup
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    entity_name: Optional[str] = None
    parent_entity_id: Optional[str] = None
    title: str
    rationale: str
    evidence: Dict[str, Any] = Field(default_factory=dict)
    current_state: Dict[str, Any] = Field(default_factory=dict)
    proposed_state: Dict[str, Any] = Field(default_factory=dict)
    impact: ImpactProjection = Field(default_factory=ImpactProjection)
    confidence_score: float = 0.5
    risk_level: RiskLevel = RiskLevel.LOW
    generated_by: str = "rule"
    policy_flags: List[str] = Field(default_factory=list)
    prerequisites: List[str] = Field(default_factory=list)
    priority_order: int = 100


# ── Scan Result Output ───────────────────────────────────────────────────────

class ExecutiveSummary(BaseModel):
    spend_analyzed: float = 0.0
    conversions_analyzed: float = 0.0
    wasted_spend_estimate: float = 0.0
    missed_opportunity_estimate: float = 0.0
    projected_conversion_lift_low: float = 0.0
    projected_conversion_lift_high: float = 0.0
    projected_cpa_improvement_pct: float = 0.0
    confidence_score: float = 0.5
    risk_score: float = 0.3
    safe_change_count: int = 0
    moderate_change_count: int = 0
    high_risk_change_count: int = 0
    total_recommendations: int = 0


class ScanResult(BaseModel):
    summary: ExecutiveSummary
    narrative: str
    recommendations: List[RecommendationOutput] = Field(default_factory=list)
    snapshot: AccountSnapshot
