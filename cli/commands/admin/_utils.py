from cli import utils
from cli.services.contracts.contract_service import Address
from cli.services.contracts.sp_registry import SPRegistryProvider, SPRegistrySLIThresholds
from cli.services.sp_registry_db import SPRegistryDB


def get_db_sps(db_url: str, kyc_status: str = None, id: int = None) -> list[SPRegistryProvider]:
    # TODO
    def retrievability_guarantees_to_bps(guarantees: list[str]) -> int:
        def _retrievability_guarantee_to_bps(guarantee: str) -> int:
            if guarantee == "hot":
                return 10000  # 100 %
            elif guarantee == "sometimes":
                return 8000  # 80 %
            elif guarantee == "cold":
                return 5000  # 50 %
            else:
                raise ValueError(f"Unknown retrievability guarantee: {guarantee}")

        return max([_retrievability_guarantee_to_bps(g) for g in guarantees]) if guarantees else 0

    # TODO
    def bandwidth_tiers_to_mbps(tiers: list[str]) -> int:
        def _bandwidth_tier_to_mbps(tier: str) -> int:
            if tier == "fast":
                return 1000
            elif tier == "normal":
                return 500
            else:
                raise ValueError(f"Unknown bandwidth tier: {tier}")

        return max([_bandwidth_tier_to_mbps(tier) for tier in tiers]) if tiers else 0

    # TODO
    def price_per_tib_to_price_per_sector(price_tib_per_month: float, payment_types: list[str]) -> int:
        if len(payment_types) != 1 or payment_types[0] != "USDFC":
            raise ValueError(f"Unsupported payment type: {payment_types[0]}")

        # Convert price from per TiB to per sector (32 GiB)
        result = price_tib_per_month * 1024 / 32
        if result != int(result):
            raise ValueError(f"Price per sector must be an integer, got {result} from price_tib_per_month={price_tib_per_month}")

        return int(result)

    organizations = SPRegistryDB(db_url).get_providers(kyc_status, id)
    result: list[SPRegistryProvider] = []

    for org in organizations:
        if org.deal_duration_max_months * 30 > 1278:
            if not utils.ask_user_confirm(
                f"Provider {org.id} has max deal duration of {org.deal_duration_max_months} months, "
                f"which exceeds the SPRegistry contract limit of 1278 days (42 months). It will be truncated to 1278 days. Return this provider?",
                default_answer=True): continue

        if Address.is_filecoin_address(org.organization_address):
            # organization_address = Address.from_filecoin_address(org.organization_address)
            organization_address = "0x5CF0365dA2F0a83c70Dfb4b96067c0e3cd2Ea951"  # TODO
            if not utils.ask_user_confirm(
                f"Converted provider {org.id} Filecoin organization_address {org.organization_address} to EVM address {organization_address}. Return this provider?",
                default_answer=True): continue

        else:
            organization_address = org.organization_address

        if Address.is_filecoin_address(org.payment_address_evm):
            raise Exception(f"Provider {org.id} has payment_address_evm {org.payment_address_evm} which is a Filecoin address, expected EVM address")

        # TODO
        result.append(SPRegistryProvider(
            provider_id=org.id,  # TODO assumes db id == smart contract id
            organization_address=organization_address,
            capabilities=SPRegistrySLIThresholds(
                retrievability_bps=retrievability_guarantees_to_bps(org.retrievability_guarantees),
                bandwidth_mbps=bandwidth_tiers_to_mbps(org.bandwidth_tier),
                latency_ms=100,  # TODO
                indexing_pct=100,  # TODO
            ),
            available_bytes=5 * 1024 * 1024 * 1024,
            price_per_sector_per_month=price_per_tib_to_price_per_sector(org.min_price_per_tib_usd, org.payment_types),
            min_deal_duration_days=org.deal_duration_min_months * 30,  # PoRep market smart contracts assumes month == 30 days
            max_deal_duration_days=min(org.deal_duration_max_months * 30, 1278),  # PoRep market smart contracts assumes month == 30 days
            payee_address=org.payment_address_evm
        ))

    return result


def get_devnet_sps() -> list[SPRegistryProvider]:
    return [
        SPRegistryProvider(provider_id=1009,
                           organization_address="0x5CF0365dA2F0a83c70Dfb4b96067c0e3cd2Ea951",
                           capabilities=SPRegistrySLIThresholds(
                               retrievability_bps=10000,
                               bandwidth_mbps=10000,
                               latency_ms=7,
                               indexing_pct=100),
                           available_bytes=94359739998368,
                           price_per_sector_per_month=0,
                           min_deal_duration_days=2,
                           max_deal_duration_days=1278,
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
                           max_deal_duration_days=1278,
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
                           max_deal_duration_days=1278,
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
                           max_deal_duration_days=1278,
                           payee_address="0x5CF0365dA2F0a83c70Dfb4b96067c0e3cd2Ea951"),
    ]
