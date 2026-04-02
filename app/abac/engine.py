import os
import casbin

ABAC_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(ABAC_DIR, "abac_model.conf")
POLICY_PATH = os.path.join(ABAC_DIR, "abac_policy.csv")

RESTRICTED_MARKER = "__RESTRICTED__"

# Tier-Hierarchie: jeder Tier erbt die Rechte aller niedrigeren Tiers.
# Der compound subject "stahlwerk_preferred" erweitert "stahlwerk" (Standard).
# Der compound subject "stahlwerk_strategic" erweitert "stahlwerk_preferred".
TIER_HIERARCHY: dict[str, list[str]] = {
    "standard":  ["stahlwerk"],
    "preferred": ["stahlwerk", "stahlwerk_preferred"],
    "strategic": ["stahlwerk", "stahlwerk_preferred", "stahlwerk_strategic"],
}


class ABACEngine:
    def __init__(self, model_path: str = MODEL_PATH, policy_path: str = POLICY_PATH):
        self.enforcer = casbin.Enforcer(model_path, policy_path)

    def can_access_field(self, role: str, resource_type: str, field: str) -> bool:
        """Einfache Prüfung ohne Tier-Kontext (abwärtskompatibel)."""
        return self.enforcer.enforce(role, resource_type, "read", field)

    def can_access_field_tiered(
        self, role: str, tier: str | None, resource_type: str, field: str
    ) -> bool:
        """
        Tier-bewusste Prüfung für Stahlwerk-Akteure.
        Für alle anderen Rollen (metallverarbeiter, haendler) wird der Tier ignoriert
        und die einfache Prüfung verwendet.

        Beispiel:
          - role="stahlwerk", tier="preferred" → prüft [stahlwerk, stahlwerk_preferred]
          - role="stahlwerk", tier="strategic" → prüft [stahlwerk, stahlwerk_preferred, stahlwerk_strategic]
          - role="haendler",  tier=irgendwas   → prüft [haendler]
        """
        if role != "stahlwerk" or not tier:
            return self.can_access_field(role, resource_type, field)
        roles_to_check = TIER_HIERARCHY.get(tier, ["stahlwerk"])
        return any(
            self.enforcer.enforce(r, resource_type, "read", field)
            for r in roles_to_check
        )

    def can_write(self, role: str, resource_type: str) -> bool:
        return self.enforcer.enforce(role, resource_type, "write", "*")

    def filter_dict(self, role: str, resource_type: str, data: dict) -> dict:
        """
        Gibt ein Dict zurück, bei dem nicht erlaubte Felder mit RESTRICTED_MARKER
        markiert sind. Kein Tier-Kontext (abwärtskompatibel).
        """
        filtered = {}
        for field, value in data.items():
            if self.can_access_field(role, resource_type, field):
                filtered[field] = value
            else:
                filtered[field] = RESTRICTED_MARKER
        return filtered

    def filter_dict_tiered(
        self, role: str, tier: str | None, resource_type: str, data: dict
    ) -> dict:
        """
        Wie filter_dict, aber mit Tier-Kontext für Stahlwerk-Akteure.
        Kernfunktion für die ABAC-Demo auf Seite 5.
        """
        filtered = {}
        for field, value in data.items():
            if self.can_access_field_tiered(role, tier, resource_type, field):
                filtered[field] = value
            else:
                filtered[field] = RESTRICTED_MARKER
        return filtered

    def filter_batch_fields(self, role: str, batch_dict: dict) -> dict:
        return self.filter_dict(role, "scrapbatch", batch_dict)

    def filter_batch_fields_tiered(
        self, role: str, tier: str | None, batch_dict: dict
    ) -> dict:
        return self.filter_dict_tiered(role, tier, "scrapbatch", batch_dict)

    def filter_chemical_fields(self, role: str, chem_dict: dict) -> dict:
        return self.filter_dict(role, "chemical", chem_dict)

    def filter_chemical_fields_tiered(
        self, role: str, tier: str | None, chem_dict: dict
    ) -> dict:
        return self.filter_dict_tiered(role, tier, "chemical", chem_dict)

    def filter_logistics_fields(self, role: str, logistics_dict: dict) -> dict:
        return self.filter_dict(role, "logistics", logistics_dict)

    def get_accessible_fields(self, role: str, resource_type: str) -> list[str]:
        """Gibt alle Felder zurück, auf die diese Rolle Zugriff hat."""
        all_policies = self.enforcer.get_policy()
        accessible = []
        for policy in all_policies:
            if len(policy) >= 5:
                sub_role, obj_type, act, field, effect = policy[:5]
                if (
                    sub_role == role
                    and obj_type == resource_type
                    and act == "read"
                    and effect == "allow"
                ):
                    accessible.append(field)
        return accessible

    def get_accessible_fields_tiered(
        self, role: str, tier: str | None, resource_type: str
    ) -> list[str]:
        """
        Gibt alle Felder zurück, auf die diese Rolle mit dem gegebenen Tier Zugriff hat.
        Für die Policy-Legende auf Seite 5.
        """
        if role != "stahlwerk" or not tier:
            return self.get_accessible_fields(role, resource_type)
        roles_to_check = TIER_HIERARCHY.get(tier, ["stahlwerk"])
        seen = set()
        accessible = []
        all_policies = self.enforcer.get_policy()
        for policy in all_policies:
            if len(policy) >= 5:
                sub_role, obj_type, act, field, effect = policy[:5]
                if (
                    sub_role in roles_to_check
                    and obj_type == resource_type
                    and act == "read"
                    and effect == "allow"
                    and field not in seen
                ):
                    seen.add(field)
                    accessible.append(field)
        return accessible

    def get_policy_rule_for_field(
        self, role: str, tier: str | None, resource_type: str, field: str
    ) -> str | None:
        """
        Gibt den Policy-Regeltext zurück, der den Zugriff auf ein Feld erlaubt oder sperrt.
        Wird für die Legende auf Seite 5 verwendet.
        """
        roles_to_check = (
            TIER_HIERARCHY.get(tier, ["stahlwerk"])
            if role == "stahlwerk" and tier
            else [role]
        )
        all_policies = self.enforcer.get_policy()
        for policy in all_policies:
            if len(policy) >= 5:
                sub_role, obj_type, act, p_field, effect = policy[:5]
                if (
                    sub_role in roles_to_check
                    and obj_type == resource_type
                    and act == "read"
                    and (p_field == field or p_field == "*")
                    and effect == "allow"
                ):
                    return f"p, {sub_role}, {obj_type}, {act}, {p_field}, {effect}"
        return None


# Singleton-Instanz
_engine_instance = None


def get_abac_engine() -> ABACEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = ABACEngine()
    return _engine_instance
