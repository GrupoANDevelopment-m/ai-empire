"""CRM backend — real HubSpot / Salesforce REST."""
import os, sys, importlib.util
_s = importlib.util.spec_from_file_location(
    "crm_api", "/workspace/ai-empire/.skills/_shared/api.py")
api = importlib.util.module_from_spec(_s); _s.loader.exec_module(api)


def backend() -> str:
    return os.getenv("CRM_PROVIDER", "hubspot").lower()


def _cfg():
    if backend() == "salesforce":
        d = api.need("SF_INSTANCE_URL", "SF_ACCESS_TOKEN", provider="Salesforce")
        return "salesforce", api.bearer(d["SF_ACCESS_TOKEN"]), d["SF_INSTANCE_URL"].rstrip("/")
    t = api.need("HUBSPOT_TOKEN", provider="HubSpot")["HUBSPOT_TOKEN"]
    return "hubspot", api.bearer(t), "https://api.hubapi.com"


async def call(method, path, body=None, params=None):
    kind, h, base = _cfg()
    return await api.request(method, base + path, headers=h,
                             json_body=body, params=params)


def norm_contact(p):
    """Normalize HubSpot/Salesforce contact -> common shape."""
    if backend() == "salesforce":
        return {"id": p.get("Id"), "email": p.get("Email"),
                "first_name": p.get("FirstName"), "last_name": p.get("LastName"),
                "company": p.get("Company") or p.get("Account", {}).get("Name"),
                "phone": p.get("Phone"), "created": p.get("CreatedDate")}
    pr = p.get("properties", {})
    return {"id": p.get("id"),
            "email": pr.get("email"), "first_name": pr.get("firstname"),
            "last_name": pr.get("lastname"),
            "company": pr.get("company"), "phone": pr.get("phone"),
            "created": p.get("createdAt")}


def norm_deal(p):
    if backend() == "salesforce":
        st = p.get("StageName")
        return {"id": p.get("Id"), "name": p.get("Name"), "amount": p.get("Amount"),
                "stage": st, "close_date": p.get("CloseDate"),
                "probability": p.get("Probability")}
    pr = p.get("properties", {})
    return {"id": p.get("id"), "name": pr.get("dealname"), "amount": pr.get("amount"),
            "stage": pr.get("dealstage"), "close_date": pr.get("closedate"),
            "deal_id": p.get("dealId")}
