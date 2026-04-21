import humanfriendly

from cli import utils
from cli.commands import utils as commands_utils
from cli.services.contracts.contract_service import Address
from cli.services.contracts.sp_registry import SPRegistryProvider, SPRegistrySLIThresholds
from cli.services.contracts.usdc_token import USDCToken
from cli.services.sp_registry_db import SPRegistryDB


# TODO LATER extract   # PoRep Market smart contracts assumes month == 30 days   to separate function
def get_db_sps(db_url: str,
               kyc_status: str | None = None,
               organization_id: int | None = None,
               indexing_pct: int = 0,
               miner_id: int | None = None,
               organization_address: str | None = None) -> list[SPRegistryProvider]:
    #
    def retrievability_guarantees_to_bps(guarantees: list[str]) -> int:
        def _retrievability_guarantee_to_bps(guarantee: str) -> int:
            DECIMALS = 2
            DECIMALS_MULTIPLIER = 10 ** DECIMALS

            if guarantee == "hot":
                return 90 * DECIMALS_MULTIPLIER  # 90 %
            elif guarantee == "sometimes":
                return 75 * DECIMALS_MULTIPLIER  # 75 %
            elif guarantee == "rarely":
                return 0 * DECIMALS_MULTIPLIER  # 0 %
            else:
                raise ValueError(f"Unknown retrievability guarantee: {guarantee}")

        return max([_retrievability_guarantee_to_bps(g) for g in guarantees]) if guarantees else 0

    def retrievability_guarantees_to_latency_ms(guarantees: list[str]) -> int:
        def _retrievability_guarantee_to_latency_ms(guarantee: str) -> int:
            if guarantee == "hot":
                return 20 * 1000  # 20 seconds
            elif guarantee == "sometimes":
                return 20 * 1000  # 20 seconds
            elif guarantee == "rarely":
                return 24 * 60 * 60 * 1000  # 24 hours
            else:
                raise ValueError(f"Unknown retrievability guarantee: {guarantee}")

        return min([_retrievability_guarantee_to_latency_ms(g) for g in guarantees]) if guarantees else 0

    def bandwidth_tiers_to_mbps(tiers: list[str]) -> int:
        def _bandwidth_tier_to_mbps(tier: str) -> int:
            if tier == "fast":
                return 1000  # 1 Gbps
            elif tier == "normal":
                return 300  # 300 Mbps
            elif tier == "slow":
                return 1  # 1 Mbps
            else:
                raise ValueError(f"Unknown bandwidth tier: {tier}")

        return max([_bandwidth_tier_to_mbps(tier) for tier in tiers]) if tiers else 0

    def price_per_tib_tokens_to_per_sector(price_per_tib_tokens: float, payment_types: list[str]) -> int:
        if not payment_types or len(payment_types) != 1 or payment_types[0] != "axlUSDC":
            raise ValueError(f"Unsupported payment type: {payment_types}")

        price_per_tib = utils.to_wei(price_per_tib_tokens, USDCToken().decimals())
        sectors_per_tib = 1024 ** 4 // commands_utils.SECTOR_SIZE_BYTES
        result = price_per_tib / sectors_per_tib

        if result != int(result):
            raise ValueError(f"Precision lost: {result:.10f} != {int(result)}")

        return int(result)

    #

    result: list[SPRegistryProvider] = []
    organizations = SPRegistryDB(db_url).get_organizations(kyc_status=kyc_status,
                                                           organization_id=organization_id,
                                                           miner_id=miner_id,
                                                           organization_address=organization_address)

    for org in organizations:
        if Address.is_filecoin_address(org.payment_address_evm):
            utils.ask_user_ok(
                f"Organization {org.organization_address} [db_id {org.id}] has payment_address_evm {org.payment_address_evm} which is a Filecoin f-address, "
                f"expected EVM 0x-address. "
                f"Cannot return SPs from this organization")
            continue

        if org.deal_duration_min_months < 0:
            utils.ask_user_ok(
                f"Organization {org.organization_address} [db_id {org.id}] has invalid min deal duration of {org.deal_duration_min_months} months. "
                f"Cannot return SPs from this organization")
            continue

        if org.kyc_status.strip().lower() != "approved":
            if not utils.ask_user_confirm(
                    f"Organization {org.organization_address} [db_id {org.id}] has kyc_status {org.kyc_status}, which is not approved. "
                    f"Return SPs from this organization?",
                    default_answer=bool(organization_id)):
                continue

        # TODO LATER get 1278 from smart contract
        if org.deal_duration_max_months * 30 > 1278:  # PoRep Market smart contracts assumes month == 30 days
            max_deal_duration_days = 42 * 30  # 42 months

            if not utils.ask_user_confirm(
                    f"Organization {org.organization_address} [db_id {org.id}] has max deal duration of {org.deal_duration_max_months * 30} days "
                    f"which exceeds the SPRegistry contract limit of {max_deal_duration_days} days. It will be truncated to this value. "
                    f"Return SPs from this organization?",
                    default_answer=True):
                continue
        else:
            max_deal_duration_days = org.deal_duration_max_months * 30  # PoRep Market smart contracts assumes month == 30 days

        # TODO LATER get minimum deral duration from smart contracts
        if org.deal_duration_min_months * 30 < 180:  # PoRep Market smart contracts assumes month == 30 days
            min_deal_duration_days = 6 * 30  # 6 months

            if not utils.ask_user_confirm(
                    f"Organization {org.organization_address} [db_id {org.id}] has min deal duration of {org.deal_duration_min_months * 30} days "
                    f"which is below the SPRegistry contract minimum of {min_deal_duration_days} days. It will be increased to this value. "
                    f"Return SPs from this organization?",
                    default_answer=True):
                continue
        else:
            min_deal_duration_days = org.deal_duration_min_months * 30  # PoRep Market smart contracts assumes month == 30 days

        if min_deal_duration_days > max_deal_duration_days:  # PoRep Market smart contracts assumes month == 30 days
            utils.ask_user_ok(
                f"Organization {org.organization_address} [db_id {org.id}] has min deal duration of {min_deal_duration_days} days, "
                f"which exceeds the max deal duration of {max_deal_duration_days} days. "
                f"Cannot return SPs from this organization")
            continue

        if Address.is_filecoin_address(org.organization_address):
            # TODO LATER remove me
            _MOCK_F_ORG_ADDR = utils.get_env_required("_MOCK_F_ORG_ADDR", default="", required_type=Address).strip().lower()
            organization_address = Address(_MOCK_F_ORG_ADDR) if _MOCK_F_ORG_ADDR else Address.from_filecoin_address(org.organization_address)

            if not utils.ask_user_confirm(
                    f"Converted organization {org.organization_address} [db_id {org.id}] Filecoin f-organization_address "
                    f"{org.organization_address} to EVM 0x-address {organization_address}. "
                    f"Return SPs from this organization?",
                    default_answer=True):
                continue
        else:
            organization_address = org.organization_address

        #

        for org_miner_id in org.miner_ids:
            # noinspection PyArgumentList
            result.append(SPRegistryProvider(
                provider_id=org_miner_id,
                organization_address=organization_address,
                capabilities=SPRegistrySLIThresholds(
                    retrievability_bps=retrievability_guarantees_to_bps(org.retrievability_guarantees),
                    bandwidth_mbps=bandwidth_tiers_to_mbps(org.bandwidth_tier),
                    latency_ms=retrievability_guarantees_to_latency_ms(org.retrievability_guarantees),
                    indexing_pct=indexing_pct,
                ),
                available_bytes=humanfriendly.parse_size(org.capacity_commitment),
                price_per_sector_per_month=price_per_tib_tokens_to_per_sector(org.min_price_per_tib_usd, org.payment_types),
                min_deal_duration_days=min_deal_duration_days,
                max_deal_duration_days=max_deal_duration_days,
                payee_address=org.payment_address_evm
            ))

    if miner_id is not None and result:
        result = [sp for sp in result if sp.provider_id == miner_id]

    return result


def get_devnet_sps() -> list[SPRegistryProvider]:
    # noinspection PyArgumentList
    return [
        SPRegistryProvider(provider_id=1009,
                           organization_address="0x5CF0365dA2F0a83c70Dfb4b96067c0e3cd2Ea951",
                           capabilities=SPRegistrySLIThresholds(
                               retrievability_bps=1000,
                               bandwidth_mbps=1000,
                               latency_ms=7,
                               indexing_pct=100),
                           available_bytes=94359739998361,
                           price_per_sector_per_month=2,
                           min_deal_duration_days=2,
                           max_deal_duration_days=1200,
                           payee_address="0x5CF0365dA2F0a83c70Dfb4b96067c0e3cd2Ea951"),
        SPRegistryProvider(provider_id=1000,
                           organization_address="0xB36a73Ba0f2fEF6a813F6cbEe26B16DA5cbf169C",
                           capabilities=SPRegistrySLIThresholds(
                               retrievability_bps=9999,
                               bandwidth_mbps=998,
                               latency_ms=100,
                               indexing_pct=99),
                           available_bytes=94359739998368,
                           price_per_sector_per_month=2,
                           min_deal_duration_days=2,
                           max_deal_duration_days=1200,
                           payee_address="0xB36a73Ba0f2fEF6a813F6cbEe26B16DA5cbf169C"),
        SPRegistryProvider(provider_id=1001,
                           organization_address="0x5CF0365dA2F0a83c70Dfb4b96067c0e3cd2Ea951",
                           capabilities=SPRegistrySLIThresholds(
                               retrievability_bps=8000,
                               bandwidth_mbps=500,
                               latency_ms=200,
                               indexing_pct=80
                           ),
                           available_bytes=94359739998368,
                           price_per_sector_per_month=0,
                           min_deal_duration_days=1,
                           max_deal_duration_days=1200,
                           payee_address="0x5CF0365dA2F0a83c70Dfb4b96067c0e3cd2Ea951"),
        SPRegistryProvider(provider_id=1002,
                           organization_address="0x5CF0365dA2F0a83c70Dfb4b96067c0e3cd2Ea951",
                           capabilities=SPRegistrySLIThresholds(
                               retrievability_bps=5000,
                               bandwidth_mbps=100,
                               latency_ms=500,
                               indexing_pct=50),
                           available_bytes=10 * 1024 * 1024 * 1024,
                           price_per_sector_per_month=100,
                           min_deal_duration_days=1,
                           max_deal_duration_days=1200,
                           payee_address="0x5CF0365dA2F0a83c70Dfb4b96067c0e3cd2Ea951"),
    ]
