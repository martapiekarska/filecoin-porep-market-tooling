import json
from datetime import datetime

import psycopg

from cli import utils


@utils.json_dataclass()
class SPRegistryDBProvider:
    id: int
    name: str
    miner_ids: list[str]
    accepted_client_geographies: list[str]
    payment_types: list[str]
    retrievability_guarantees: list[str]
    bandwidth_tier: list[str]
    service_frequency: list[str]
    data_types: list[str]
    customer_support_email: str
    contact_details: str
    onboarding_bandwidth: str
    payment_address: str
    organization_address: str
    kyc_session_id: str | None
    kyc_session_url: str | None
    kyc_status: str
    kyc_completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    geographical_location: list[str]
    kyc_email: str
    payment_address_evm: str
    deal_duration_min_months: int
    deal_duration_max_months: int
    min_price_per_tib_usd: float
    sp_software: list[str]

    @staticmethod
    def from_db(data) -> "SPRegistryDBProvider":
        return SPRegistryDBProvider(
            id=data[0],
            name=data[1],
            miner_ids=data[2],
            accepted_client_geographies=data[3],
            payment_types=data[4],
            retrievability_guarantees=data[5],
            bandwidth_tier=json.loads(f"[{data[6][1:-1]}]"),
            service_frequency=data[7],
            data_types=data[8],
            customer_support_email=data[9],
            contact_details=data[10],
            onboarding_bandwidth=data[11],
            payment_address=data[12],
            organization_address=data[13],
            kyc_session_id=data[14],
            kyc_session_url=data[15],
            kyc_status=data[16],
            kyc_completed_at=f"{data[17]}",
            created_at=data[18],
            updated_at=data[19],
            geographical_location=data[20],
            kyc_email=data[21],
            payment_address_evm=data[22],
            deal_duration_min_months=data[23],
            deal_duration_max_months=data[24],
            min_price_per_tib_usd=data[25],
            sp_software=data[26]
        )


class SPRegistryDB:
    def __init__(self, db_url: str):
        self.db_url = db_url

    def get_providers(self, kyc_status: str = None, provider_id: int = None) -> list[SPRegistryDBProvider]:
        query = "SELECT * FROM providers WHERE true"
        params = []

        if kyc_status is not None:
            query += " AND kyc_status = %s"
            params.append(kyc_status)

        if provider_id is not None:
            query += " AND id = %s"
            params.append(provider_id)

        with psycopg.connect(self.db_url) as conn:
            providers = [
                SPRegistryDBProvider.from_db(p)
                for p in conn.execute(query, params).fetchall()
            ]

        return providers
