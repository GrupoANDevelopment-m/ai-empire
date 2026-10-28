"""company_enrichment — real firmographic lookup."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_TD = os.path.dirname(os.path.abspath(__file__))
import importlib.util
_s = importlib.util.spec_from_file_location(
    "b2b_api", "/workspace/ai-empire/.skills/_shared/api.py")
api = importlib.util.module_from_spec(_s); _s.loader.exec_module(api)


async def company_enrichment(domain_or_name: str,
                             include_contacts: bool = True) -> dict:
    """
    Enrich a company with real firmographic data.

    Uses (in order): Clearbit Company API, then the company website footer
    (real HTTP fetch + extraction). Never invents data — unknown fields are null.

    Args:
        domain_or_name: company domain (acme.com) or name
        include_contacts: also parse the site for public contact emails

    Returns:
        {"ok": True, "domain": str, "name": str, "employees": int|null,
         "industry": str|null, "description": str|null, "source": str}
    """
    if not domain_or_name.strip():
        raise ValueError("domain_or_name is required")

    domain = domain_or_name.lower().strip()
    if " " in domain:
        slug = re.sub(r"[^a-z0-9]+", "", domain)
        domain = f"{slug}.com"
        name_guess = domain_or_name.strip()
    else:
        name_guess = None

    source, data = "none", {}
    key = os.getenv("CLEARBIT_API_KEY", "").strip()
    if key:
        r = await api.request("GET",
            f"https://company.clearbit.com/v2/companies/find",
            params={"domain": domain},
            headers={"Authorization": f"Bearer {key}"})
        if r.get("ok") and isinstance(r.get("body"), dict):
            b = r["body"]
            data = {"name": b.get("name"),
                    "description": b.get("description"),
                    "industry": (b.get("category") or {}).get("sector"),
                    "employees": b.get("metrics", {}).get("employees"),
                    "location": (b.get("geo") or {}).get("city"),
                    "country": (b.get("geo") or {}).get("country"),
                    "logo": (b.get("logo") or {}).get("url"),
                    "twitter": b.get("twitter", {}).get("handle"),
                    "linkedin": b.get("linkedin", {}).get("handle"),
                    "founded_year": b.get("foundedYear")}
            source = "clearbit"
    if not data:
        r = await api.request("GET", f"https://{domain}",
                              headers={"User-Agent": "Mozilla/5.0 (compatible; AIEmpire/1.0)"})
        if r.get("ok") and isinstance(r.get("body"), str):
            import html as _html
            html = r["body"]
            title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
            meta = re.search(
                r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+'
                r'content=["\'](.*?)["\']', html, re.S | re.I)
            og_site = re.search(
                r'<meta[^>]+property=["\']og:site_name["\'][^>]+content=["\'](.*?)["\']',
                html, re.S | re.I)

            def clean(s):
                return re.sub(r"\s+", " ", _html.unescape(s)).strip() if s else None

            name = clean(og_site.group(1)) if og_site else clean(title.group(1) if title else None)
            # A redirect or bare "301 Moved Permanently" title is not a company name
            if name and re.fullmatch(r"\d{3}\s+Moved\s+Permanently.*", name, re.I):
                name = None
            data = {"name": name,
                    "description": clean(meta.group(1)) if meta else None,
                    "industry": None, "employees": None}
            source = "website"
            if include_contacts:
                emails = sorted(set(re.findall(
                    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", html)))
                # placeholder / non-contact addresses that appear in boilerplate
                junk = ("example.com", "sentry.io", "w3.org", "schema.org",
                        "yourdomain", "yourdomain.com", "email.com", "domain.com",
                        "test.com", "mydomain", "site.com", "yoursite", "localhost",
                        "sentry", "wixpress", "cloudflare", "@2x", "noreply@")
                data["public_emails"] = [
                    e for e in emails[:40]
                    if not any(j in e.lower() for j in junk)
                    and not re.match(r"^(you|your|seu|test|user|name|email|someone|anyone)", e.lower())
                ][:10]

    if not data:
        return {"ok": False, "error": f"no enrichment source could reach {domain}",
                "domain": domain,
                "hint": "set CLEARBIT_API_KEY for real firmographics, or pass a valid domain"}

    return {"ok": True, "domain": domain, "name": data.get("name") or name_guess or domain,
            "employees": data.get("employees"), "industry": data.get("industry"),
            "description": data.get("description"),
            "location": data.get("location"), "country": data.get("country"),
            "logo": data.get("logo"),
            "socials": {"twitter": data.get("twitter"), "linkedin": data.get("linkedin")},
            "public_emails": data.get("public_emails", []) if include_contacts else [],
            "founded_year": data.get("founded_year"),
            "source": source,
            "note": "null fields mean the upstream source did not publish them"}
