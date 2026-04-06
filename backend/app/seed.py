"""
Demo Tenant Seed Script + Mock Data Generator

Run with: python -m app.seed
"""
import asyncio
import uuid
from datetime import datetime, date, timedelta, timezone
import random

from app.core.database import async_session_factory, engine, Base
from app.core.security import hash_password, encrypt_token
from app.models import *  # noqa


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as db:
        # ── DEMO USER ─────────────────────────────────────────────
        user_id = str(uuid.uuid4())
        user = User(
            id=user_id,
            email="demo@getintelliads.com",
            password_hash=hash_password("demo1234"),
            full_name="Demo User",
        )
        db.add(user)

        # ── DEMO TENANT ───────────────────────────────────────────
        tenant_id = str(uuid.uuid4())
        tenant = Tenant(
            id=tenant_id,
            name="Ace Locksmith Dallas",
            industry="locksmith",
            timezone="America/Chicago",
            autonomy_mode="semi_auto",
            risk_tolerance="low",
            daily_budget_cap_micros=100_000_000,
            weekly_change_cap_pct=15,
            tier="pro",
        )
        db.add(tenant)

        tu = TenantUser(tenant_id=tenant_id, user_id=user_id, role="owner")
        db.add(tu)

        # ── BUSINESS PROFILE ──────────────────────────────────────
        profile = BusinessProfile(
            tenant_id=tenant_id,
            website_url="https://www.acelocksmithdallas.com",
            description="24/7 emergency locksmith services in Dallas-Fort Worth. Licensed, bonded & insured.",
            industry_classification="locksmith",
            primary_conversion_goal="calls",
            phone="(214) 555-0123",
            avg_ticket_estimate=150,
            services_json={"list": [
                "Emergency Lockout", "Car Key Replacement", "Lock Rekey",
                "Commercial Locksmith", "Residential Locksmith", "Safe Opening",
                "Key Fob Programming", "Master Key Systems",
            ]},
            locations_json={"cities": [
                "Dallas", "Fort Worth", "Arlington", "Plano", "Irving",
                "Garland", "Frisco", "McKinney", "Richardson", "Carrollton",
            ]},
            usp_json={"list": [
                "15-minute response time", "Licensed & insured",
                "Upfront pricing, no hidden fees", "24/7 availability",
            ]},
            brand_voice_json={"tone": "urgent", "style": "direct", "keywords": ["fast", "reliable", "trusted"]},
            offers_json={"list": [
                "$20 Off Any Service", "Free Estimates", "Senior & Military Discount 10%",
            ]},
            trust_signals_json={"list": [
                "Licensed & Bonded", "500+ 5-Star Reviews", "15+ Years Experience",
                "BBB A+ Rated", "Background-Checked Technicians",
            ]},
            competitor_targets_json={"list": ["Pop-A-Lock Dallas", "Mr. Rekey Locksmith", "Dallas Lock & Key"]},
            constraints_json={"hours": "24/7", "emergency": True},
            gbp_link="https://g.page/ace-locksmith-dallas",
        )
        db.add(profile)

        # ── MOCK GOOGLE ADS INTEGRATION ───────────────────────────
        fake_token = encrypt_token("mock-refresh-token-for-demo")
        integration = IntegrationGoogleAds(
            tenant_id=tenant_id,
            customer_id="1234567890",
            refresh_token_encrypted=fake_token,
            access_token_cache="mock-access-token",
            account_name="Ace Locksmith Dallas - Google Ads",
            is_active=True,
            health_score=82,
            last_sync_at=datetime.now(timezone.utc),
        )
        db.add(integration)

        # ── MOCK CAMPAIGNS ────────────────────────────────────────
        campaigns_data = [
            {"name": "Emergency Lockout - Search", "type": "SEARCH", "status": "ENABLED", "budget": 50_000_000, "bid": "MAXIMIZE_CONVERSIONS", "obj": "calls"},
            {"name": "Car Key Replacement - Search", "type": "SEARCH", "status": "ENABLED", "budget": 30_000_000, "bid": "MAXIMIZE_CONVERSIONS", "obj": "calls"},
            {"name": "Commercial Locksmith - Search", "type": "SEARCH", "status": "ENABLED", "budget": 25_000_000, "bid": "TARGET_CPA", "obj": "leads"},
            {"name": "Brand - Ace Locksmith", "type": "SEARCH", "status": "ENABLED", "budget": 10_000_000, "bid": "MAXIMIZE_CLICKS", "obj": "brand"},
            {"name": "Dallas Locksmith - PMax", "type": "PERFORMANCE_MAX", "status": "PAUSED", "budget": 20_000_000, "bid": "MAXIMIZE_CONVERSION_VALUE", "obj": "leads"},
        ]

        campaign_ids = []
        for cd in campaigns_data:
            cid = str(uuid.uuid4())
            c = Campaign(
                id=cid,
                tenant_id=tenant_id,
                google_customer_id="1234567890",
                campaign_id=str(random.randint(10000000, 99999999)),
                type=cd["type"],
                name=cd["name"],
                status=cd["status"],
                objective=cd["obj"],
                budget_micros=cd["budget"],
                bidding_strategy=cd["bid"],
                is_draft=False,
            )
            db.add(c)
            campaign_ids.append(cid)

        # ── MOCK AD GROUPS + KEYWORDS + ADS ───────────────────────
        ag_data = [
            {"campaign_idx": 0, "name": "Emergency Lockout - Exact", "keywords": [
                ("emergency locksmith", "EXACT"), ("locked out of house", "EXACT"),
                ("locksmith near me", "PHRASE"), ("24 hour locksmith", "EXACT"),
            ]},
            {"campaign_idx": 0, "name": "Emergency Lockout - Phrase", "keywords": [
                ("home lockout service", "PHRASE"), ("car lockout help", "PHRASE"),
                ("lock change service", "PHRASE"),
            ]},
            {"campaign_idx": 1, "name": "Car Key Replacement", "keywords": [
                ("car key replacement", "EXACT"), ("lost car key", "PHRASE"),
                ("key fob replacement", "EXACT"), ("transponder key", "PHRASE"),
            ]},
        ]

        for agd in ag_data:
            ag_id = str(uuid.uuid4())
            ag = AdGroup(
                id=ag_id,
                tenant_id=tenant_id,
                campaign_id=campaign_ids[agd["campaign_idx"]],
                ad_group_id=str(random.randint(10000000, 99999999)),
                name=agd["name"],
                status="ENABLED",
            )
            db.add(ag)

            for kw_text, kw_match in agd["keywords"]:
                kw = Keyword(
                    tenant_id=tenant_id,
                    ad_group_id=ag_id,
                    keyword_id=str(random.randint(10000000, 99999999)),
                    text=kw_text,
                    match_type=kw_match,
                    status="ENABLED",
                    quality_score=random.choice([6, 7, 8, 9, None]),
                    cpc_bid_micros=random.randint(2_000_000, 8_000_000),
                )
                db.add(kw)

            ad = Ad(
                tenant_id=tenant_id,
                ad_group_id=ag_id,
                ad_id=str(random.randint(10000000, 99999999)),
                ad_type="RESPONSIVE_SEARCH_AD",
                headlines_json=[
                    "Emergency Locksmith Dallas", "24/7 Lockout Service",
                    "Licensed & Insured", "15-Min Response Time",
                    "Call (214) 555-0123", "$20 Off Any Service",
                    "Trusted Since 2008", "Fast & Reliable",
                ],
                descriptions_json=[
                    "Locked out? Call Ace Locksmith Dallas for fast 24/7 emergency service. Licensed & insured. $20 off!",
                    "Professional locksmith services in Dallas-Fort Worth. 15-minute response. Free estimates. Call now!",
                ],
                final_urls_json=["https://www.acelocksmithdallas.com/emergency-lockout"],
                status="ENABLED",
            )
            db.add(ad)

        # ── MOCK CONVERSIONS ──────────────────────────────────────
        for conv_data in [
            ("Phone Calls", "PHONE_CALL", True),
            ("Contact Form", "WEBPAGE", True),
            ("Direction Clicks", "WEBPAGE", False),
        ]:
            conv = Conversion(
                tenant_id=tenant_id,
                google_customer_id="1234567890",
                action_id=str(random.randint(100000, 999999)),
                name=conv_data[0],
                type=conv_data[1],
                status="ENABLED",
                is_primary=conv_data[2],
                last_verified_at=datetime.now(timezone.utc),
            )
            db.add(conv)

        # ── MOCK PERFORMANCE DATA (30 DAYS) ───────────────────────
        for i in range(30):
            d = date.today() - timedelta(days=i)
            for idx, cid in enumerate(campaign_ids[:4]):
                base_impressions = [400, 250, 180, 100][idx]
                base_clicks = [35, 20, 12, 15][idx]
                base_cost = [45_000_000, 28_000_000, 20_000_000, 8_000_000][idx]
                base_conv = [5.0, 3.0, 1.5, 2.0][idx]

                noise = random.uniform(0.7, 1.3)
                perf = PerformanceDaily(
                    tenant_id=tenant_id,
                    entity_type="campaign",
                    entity_id=cid,
                    date=d,
                    impressions=int(base_impressions * noise),
                    clicks=int(base_clicks * noise),
                    cost_micros=int(base_cost * noise),
                    conversions=round(base_conv * noise, 1),
                    conv_value=round(base_conv * noise * 150, 2),
                    ctr=round((base_clicks * noise) / (base_impressions * noise) * 100, 2),
                    cpc_micros=int(base_cost * noise / max(1, int(base_clicks * noise))),
                    cpa_micros=int(base_cost * noise / max(0.1, base_conv * noise)),
                )
                db.add(perf)

        # ── MOCK AUCTION INSIGHTS ─────────────────────────────────
        competitor_domains = ["pop-a-lock.com", "mrrekey.com", "dallaslocknkey.com", "locksmithpros.com"]
        for i in range(14):
            d = date.today() - timedelta(days=i)
            for domain in competitor_domains:
                ai = AuctionInsight(
                    tenant_id=tenant_id,
                    campaign_id=campaign_ids[0],
                    date=d,
                    competitor_domain=domain,
                    impression_share=round(random.uniform(0.1, 0.5), 3),
                    overlap_rate=round(random.uniform(0.2, 0.7), 3),
                    outranking_share=round(random.uniform(0.1, 0.6), 3),
                    top_of_page_rate=round(random.uniform(0.3, 0.8), 3),
                    abs_top_rate=round(random.uniform(0.1, 0.4), 3),
                    position_above_rate=round(random.uniform(0.1, 0.5), 3),
                )
                db.add(ai)

        # ── MOCK RECOMMENDATIONS ──────────────────────────────────
        recs_data = [
            {"cat": "waste_control", "sev": "high", "title": "Add 12 negative keywords to Emergency Lockout campaign", "risk": "low"},
            {"cat": "waste_control", "sev": "medium", "title": "Pause 3 keywords with $45 spend and 0 conversions", "risk": "low"},
            {"cat": "coverage", "sev": "medium", "title": "Add 'lock rekey near me' and 'rekey locks dallas' keywords", "risk": "low"},
            {"cat": "messaging", "sev": "low", "title": "Rotate headline: replace 'Fast & Reliable' with '5-Star Rated'", "risk": "low"},
            {"cat": "bid_budget", "sev": "medium", "title": "Increase Emergency Lockout daily budget by 10% ($5 → $5.50)", "risk": "medium"},
            {"cat": "targeting", "sev": "low", "title": "Add schedule adjustment: increase bids 20% during 10PM-6AM", "risk": "low"},
        ]
        for rd in recs_data:
            rec = Recommendation(
                tenant_id=tenant_id,
                category=rd["cat"],
                severity=rd["sev"],
                title=rd["title"],
                rationale=f"Analysis of the last 14 days shows opportunity to improve performance via {rd['cat']}.",
                expected_impact_json={"estimated_improvement": "5-15%", "timeframe": "1-2 weeks"},
                risk_level=rd["risk"],
                action_diff_json={"action": rd["cat"], "details": rd["title"]},
                status="pending",
            )
            db.add(rec)

        # ── MOCK ALERTS ───────────────────────────────────────────
        alert = Alert(
            tenant_id=tenant_id,
            type="cpa_spike",
            severity="medium",
            message="CPA for Car Key Replacement campaign increased 25% vs 30-day baseline ($28 → $35).",
            entity_ref_json={"campaign_id": campaign_ids[1]},
        )
        db.add(alert)

        # ── MOCK COMPETITOR PROFILES ──────────────────────────────
        for domain in competitor_domains[:3]:
            cp = CompetitorProfile(
                tenant_id=tenant_id,
                competitor_key=domain.replace(".", "_"),
                name=domain.split(".")[0].title(),
                domain=domain,
                landing_pages_json=[f"https://{domain}/", f"https://{domain}/services"],
                messaging_themes_json=["24/7 service", "licensed", "fast response", "affordable"],
            )
            db.add(cp)

        # ── PLAYBOOKS ─────────────────────────────────────────────
        locksmith_playbook = Playbook(
            industry="locksmith",
            goal_type="calls",
            template_json={
                "campaign_types": ["SEARCH", "CALL"],
                "default_budget_micros": 50_000_000,
                "bidding_strategy": "MAXIMIZE_CONVERSIONS",
                "keyword_themes": ["emergency locksmith", "lockout service", "lock change", "car key replacement"],
                "negative_base": ["locksmith training", "locksmith tools", "lock picking kit", "diy lock"],
                "headline_themes": ["24/7", "emergency", "fast response", "licensed"],
                "recommended_extensions": ["call", "location", "sitelink", "callout"],
            },
        )
        db.add(locksmith_playbook)

        roofing_playbook = Playbook(
            industry="roofing",
            goal_type="leads",
            template_json={
                "campaign_types": ["SEARCH"],
                "default_budget_micros": 75_000_000,
                "bidding_strategy": "TARGET_CPA",
                "keyword_themes": ["roof repair", "roof replacement", "storm damage roof", "roofing contractor"],
                "negative_base": ["roofing materials", "roofing jobs", "roofing nails", "diy roof"],
                "headline_themes": ["free estimate", "storm damage", "licensed", "local"],
                "recommended_extensions": ["call", "location", "sitelink", "structured_snippet"],
            },
        )
        db.add(roofing_playbook)

        # ── MOCK LEARNINGS ────────────────────────────────────────
        learning1 = Learning(
            industry="locksmith",
            pattern_type="headline_theme",
            pattern_json={
                "best_themes": ["24/7", "emergency", "fast response"],
                "avg_ctr_lift": 0.15,
                "keywords": ["24 hour locksmith near me", "emergency lock change"],
            },
            evidence_json={"sample_size": 42, "tenants_count": 8},
            confidence=0.78,
        )
        db.add(learning1)

        learning2 = Learning(
            industry="locksmith",
            pattern_type="negative_base",
            pattern_json={
                "negatives": ["locksmith training", "lock picking set", "locksmith course", "diy lock repair"],
                "avg_waste_prevented_pct": 0.12,
            },
            evidence_json={"sample_size": 35, "tenants_count": 6},
            confidence=0.85,
        )
        db.add(learning2)

        await db.commit()
        print("✅ Demo seed complete!")
        print(f"   Email: demo@getintelliads.com")
        print(f"   Password: demo1234")
        print(f"   Tenant: Ace Locksmith Dallas")
        print(f"   Tenant ID: {tenant_id}")


if __name__ == "__main__":
    asyncio.run(seed())
